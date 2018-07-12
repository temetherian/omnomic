#!/usr/bin/python

import datetime
import jinja2
import json
import os
import random
import uuid
import webapp2

from google.appengine.api import app_identity
from google.appengine.ext import ndb

from cards import mob
from cards import pros

import comm
import engine
import game as olj_game


JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)


class ChangeMessage(ndb.Model):
  timestamp = ndb.DateTimeProperty()
  crew_msg = ndb.TextProperty(indexed=False)
  powers_msg = ndb.TextProperty(indexed=False)

  @classmethod
  def QueryGameSince(cls, game_key, ts):
    return cls.query(ancestor=game_key).filter(cls.timestamp > ts).order(cls.timestamp)


def RecentPlayerChanges(game, player_id, ts=None):
  if ts is None:
    ts = game.prev_ts
  messages = ChangeMessage.QueryGameSince(game.key, ts).fetch()
  if player_id == game.CREW:
    return [m.crew_msg for m in messages]
  elif player_id == game.POWERS:
    return [m.powers_msg for m in messages]


def PlayerState(game, player_id):
  """Get a serializable representation of the current game state for a player.

  Args:
    game: a stack.StackGame
    player_id: (int)
  """
  state = {'acting_player': game.acting_player,
           'acting_player_actions': game.acting_player_actions,
           'crew_deck_size': len(game.crew_deck),
           'powers_deck_size': len(game.powers_deck),
           'crew_points': game.crew_points,
           'powers_points': game.powers_points,
           'office_influence': game.office.influence,
           'threat_level': game.threat_level}
  if game.prev_ts:
    state['__prev_ts'] = game.prev_ts.isoformat()
  if game.ts:
    state['__ts'] = game.ts.isoformat()
  if game.stack[-1].function == 'AcceptPly':
    expected_player = game.acting_player
    for tag in game.stack[-1].tags:
      if tag.startswith('__waiting_on:'):
        expected_player = int(tag.split(':')[1])
    if expected_player == player_id:
      state['plies'] = game.stack[-1].args
  for card in game.cards:
    if not card.position.endswith('_deck'):
      state.setdefault(card.position, []).append(card.VisibleInfo(player_id))
  for scene in game.scenes:
    if scene.position != 'scene_deck':
      state.setdefault('active_scenes', []).append(scene.VisibleInfo(player_id))
  state.update(game.PlayerStates(player_id))
  return state


class DeleteHandler(webapp2.RequestHandler):
  def get(self, game_id):
    game = olj_game.OneLastJobGame.get_by_id(game_id)
    if game:
      comm.DeleteChannel(game.crew_channel_id)
      comm.DeleteChannel(game.powers_channel_id)
      game.key.delete()
    self.response.headers['Content-Type'] = 'text/plain'
    self.response.write('BALEETED')


class CreateRandomHandler(webapp2.RequestHandler):
  def get(self):
    game_id = random.randint(100000000000, 999999999999)
    return self.redirect('/%s/create' % game_id)


class CreateHandler(webapp2.RequestHandler):
  def get(self, game_id):
    """Initialize a game."""
    game = olj_game.OneLastJobGame.get_by_id(game_id)
    if game:
      comm.DeleteChannel(game.crew_channel_id)
      comm.DeleteChannel(game.powers_channel_id)
    crew_cards = []
    # We have fixed decks for the demo.
    crew_deck = [1, 1,
                 2, 2,
                 3, 3,
                 4, 4,
                 5, 5,
                 6, 6,
                 7, 7,
                 9, 9,
                 10, 10,
                 11, 11,
                 12, 12,
                 13, 13,
                 14, 14,
                 15, 15,
                 102, 102,
                ]
    random.shuffle(crew_deck)
    for i, db_id in enumerate(crew_deck):
      card_dict = pros.CARDS[db_id]
      card_id = 1 + i
      card = olj_game.Card(
          card_id=card_id,
          db_id=db_id,
          player=1,
          position='crew_deck',
          cost=card_dict['cost'],
          card_type=card_dict['card_type'],
          play_function=card_dict['play_function'],
      )
      for option in ['unique', 'target_type', 'target_reqs', 'abilities', 'skill_cap']:
        value = card_dict.get(option)
        if value:
          setattr(card, option, value)
      crew_cards.append(card)

    boss = olj_game.Card(card_id=1000,
                         db_id=1000,
                         player=2,
                         cost=0,
                         card_type='actor',
                         position='office')
    boss.is_faceup = True
    boss.unique = True
    boss.abilities = ['Move1InfluenceHere']
    boss.card_subtypes = ['boss']
    powers_cards = [boss]
    powers_triggers = []
    powers_deck = [1001, 1001,
                   1002, 1002,
                   1003, 1003,
                   1004, 1004,
                   1005, 1005,
                   1006, 1006,
                   1007,
                   1008, 1008,
                   1009, 1009,
                   1010, 1010,
                   1011,
                   1012, 1012,
                   1013, 1013,
                   1014, 1014,
                   1015, 1015,
                   1101, 1101,
                  ]
    random.shuffle(powers_deck)
    for i, db_id in enumerate(powers_deck):
      card_dict = mob.CARDS[db_id]
      card_id = 1001 + i
      card = olj_game.Card(
          card_id=card_id,
          db_id=db_id,
          player=2,
          position='powers_deck',
          cost=card_dict['cost'],
          card_type=card_dict['card_type'],
          play_function=card_dict['play_function'],
      )
      for option in ['unique', 'target_type', 'target_reqs', 'abilities']:
        value = card_dict.get(option)
        if value:
          setattr(card, option, value)
      powers_cards.append(card)

      # Triggers don't necessarily have to be created when the card is initialized,
      # but this allows us to have effects trigger from anywhere, most importantly
      # allowing WhenDiscovered effects on complications in the Powers' deck.
      effects = card_dict.get('effects', [])
      for matcher, function, aversion_cost in effects:
        tags = []
        if aversion_cost:
          tags = ['__awaiting_input',
                  'avertable',
                  'aversioncost:%s' % aversion_cost]
        new_trigger = engine.Trigger(
            object_class='card',
            object_id=card_id,
            matcher=matcher,
            function=function,
            tags=tags)
        powers_triggers.append(new_trigger)

    game = olj_game.OneLastJobGame(cards=crew_cards + powers_cards, id=game_id)
    game.InitializeGame()
    game.reactive_triggers.extend(powers_triggers)
    game.Save()
    self.response.headers['Content-Type'] = 'text/plain'
    self.response.write('Game %s created. To reset this game, reload this page.\n\n' % game_id)
    self.response.write('Crew: %s/%s/1\n' % (self.request.host_url, game_id))
    self.response.write('Powers: %s/%s/2\n' % (self.request.host_url, game_id))


class FrontendHandler(webapp2.RequestHandler):
  def get(self, game_id, player_id):
    game = olj_game.OneLastJobGame.get_by_id(game_id)
    player_id = int(player_id)

    # This is where user authentication could go.
    # If a channel id is authenticated and deterministic, it
    # could allow a user to return to a game in progress and
    # avoid this whole creating-new-channels-every-time thing.
    channel_id = uuid.uuid4().hex
    token = comm.create_custom_token(channel_id)
    if player_id == game.CREW:
      if game.crew_channel_id != channel_id:
        comm.DeleteChannel(game.crew_channel_id)
        game.crew_channel_id = channel_id
    elif player_id == game.POWERS:
      if game.powers_channel_id != channel_id:
        comm.DeleteChannel(game.powers_channel_id)
        game.powers_channel_id = channel_id
    game.put()

    current_state = PlayerState(game, player_id)

    template_values = {'token': token,
                       'game_id': game_id,
                       'player_id': player_id,
                       'channel_id': channel_id,
                       'player': 'crew' if player_id == game.CREW else 'powers',
                       'current_state': json.dumps(current_state),
                       }
    template = JINJA_ENVIRONMENT.get_template('templates/olj.html')
    self.response.write(template.render(template_values))


class JsonHandler(webapp2.RequestHandler):
  def get(self, game_id, player_id):
    """Return current game state (scoped to requesting player) as JSON."""
    game = olj_game.OneLastJobGame.get_by_id(game_id)
    player_id = int(player_id)
    current_state = PlayerState(game, player_id)
    changes = RecentPlayerChanges(game, player_id)
    if changes:
      current_state['last_message'] = changes[-1]
    self.response.headers['Content-Type'] = 'application/json'
    self.response.write(json.dumps(current_state))


class StackHandler(webapp2.RequestHandler):
  def get(self, game_id):
    """Return current game stack as JSON."""
    game = olj_game.OneLastJobGame.get_by_id(game_id)
    stack_list = []
    for stack_item in reversed(game.stack):
      stack_list.append(stack_item.to_dict())
    self.response.headers['Content-Type'] = 'application/json'
    self.response.write(json.dumps(stack_list))


class TriggersHandler(webapp2.RequestHandler):
  def get(self, game_id):
    """Return current list of triggers as JSON."""
    game = olj_game.OneLastJobGame.get_by_id(game_id)
    trigger_list = []
    for trigger in game.reactive_triggers:
      trigger_list.append(trigger.to_dict())
    self.response.headers['Content-Type'] = 'application/json'
    self.response.write(json.dumps(trigger_list))


class ChangesHandler(webapp2.RequestHandler):
  def get(self, game_id, player_id):
    """Return all change messages for a player since the given timestamp."""
    ts_str = self.request.get('t')
    ts = datetime.datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S.%f")
    game = olj_game.OneLastJobGame.get_by_id(game_id)
    player_id = int(player_id)
    changes = RecentPlayerChanges(game, player_id, ts)
    self.response.headers['Content-Type'] = 'application/json'
    self.response.write(json.dumps(changes))


def ply(method):
  """Decorate a request handling method with the usual messaging stuff.

  Args:
    method: An action to perform on a game. Should have
      Args:
        self/handler: unused, but passed in due to being defined in a class
        game: a olj_game.OneLastJobGame
        player_id: (int) the acting player
      Returns:
        A dict of errors or None.

  Returns:
    An HTTP handler method.
  """
  def new_method(handler, game_id, player_id):
    """Get the given game, perform the requested ply, and perform messaging.

    Args:
      handler: a webapp2.RequestHandler
      game_id: the ID for the OneLastJobGame to act on
      player_id: the acting player

    Returns: None
    """
    handler.response.headers['Content-Type'] = 'application/json'
    game = olj_game.OneLastJobGame.get_by_id(game_id)
    player_id = int(player_id)
    errors = method(handler, game, player_id)
    if errors:
      handler.response.write(json.dumps(errors))
      return

    changes, plies, options = game.ProcessStack()  # returns list of state changes

    crew_msg = json.dumps(game.MessageForPlayer(changes, plies, options, 1))
    powers_msg = json.dumps(game.MessageForPlayer(changes, plies, options, 2))
    response_msg = crew_msg if player_id == 1 else powers_msg
    comm.MaybeSendToChannel(game.crew_channel_id, crew_msg)
    comm.MaybeSendToChannel(game.powers_channel_id, powers_msg)

    cm = ChangeMessage(parent=game.key,
                       timestamp=game.ts,
                       crew_msg=crew_msg,
                       powers_msg=powers_msg)
    cm.put()
    game.Save()
    handler.response.write(response_msg)
  return new_method


class ChooseResolutionHandler(webapp2.RequestHandler):
  @ply
  def post(self, game, player_id):
    valid = game.Validate(player_id, 'ChooseResolution')
    if not valid:
      return {'errors': 'Now is not the time for that.'}
    resolution = self.request.get('r')
    game.FillWaitingArgs([resolution])
    # Another pattern is something like:
    # game.StopWaiting()
    # game.Push('ChooseResolution', [resolution])


class EndTurnHandler(webapp2.RequestHandler):
  @ply
  def post(self, game, player_id):
    valid = game.Validate(player_id, 'EndTurn')
    if not valid:
      return {'errors': 'invalid move (is it your turn?)'}
    game.StopWaiting()
    game.Push('EndTurn')


class MoveCardHandler(webapp2.RequestHandler):
  @ply
  def post(self, game, player_id):
    card_id = int(self.request.get('c'))
    position = self.request.get('l')
    valid = game.Validate(player_id, 'MoveCardPly', [card_id, position])
    if not valid:
      return {'errors': 'invalid move (is it your turn?)'}
    game.StopWaiting()
    game.Push('MoveCardPly', [card_id, position])


class DrawCardHandler(webapp2.RequestHandler):
  @ply
  def post(self, game, player_id):
    """Draw a card for the player."""
    valid = game.Validate(player_id, 'DrawCardPly')
    if not valid:
      return {'errors': 'invalid move (is it your turn?)'}
    game.StopWaiting()
    game.Push('DrawCardPly')


class OffInfHandler(webapp2.RequestHandler):
  @ply
  def post(self, game, player_id):
    """Draw a card for the player."""
    valid = game.Validate(2, 'OfficeInfluencePly')
    if not valid:
      return {'errors': 'invalid move (is it your turn?)'}
    game.StopWaiting()
    game.Push('OfficeInfluencePly')


class HideoutSkillHandler(webapp2.RequestHandler):
  @ply
  def post(self, game, player_id):
    """Draw a card for the player."""
    valid = game.Validate(1, 'HideoutSkillPly')
    if not valid:
      return {'errors': 'invalid move (is it your turn?)'}
    game.StopWaiting()
    game.Push('HideoutSkillPly')


class PlayCardHandler(webapp2.RequestHandler):
  @ply
  def post(self, game, player_id):
    """Play a card."""
    card_id = int(self.request.get('c'))
    target = self.request.get('t', None)
    valid = game.Validate(player_id, 'PlayCardPly', [card_id])
    if not valid:
      return {'errors': 'invalid move (is it your turn?)'}
    game.StopWaiting()
    game.Push('PlayCardPly', [card_id, target])


class UseCardHandler(webapp2.RequestHandler):
  @ply
  def post(self, game, player_id):
    """Use a card ability."""
    card_id = int(self.request.get('c'))
    ability = self.request.get('a')
    valid = game.Validate(player_id, 'UseCardPly', [card_id])
    if not valid:
      return {'errors': 'invalid move (is it your turn?)'}
    game.StopWaiting()
    game.Push('UseCardPly', [card_id, ability])


class MulliganHandler(webapp2.RequestHandler):
  @ply
  def post(self, game, player_id):
    valid = game.Validate(player_id, 'MulliganPly')
    card_ids = [int(c) for c in self.request.get_all('cs[]')]
    if not valid:
      return {'errors': 'Not time for you to mulligan.'}
    game.StopWaiting()
    game.Push('MulliganPly', [player_id] + card_ids)


class DiscardHandler(webapp2.RequestHandler):
  @ply
  def post(self, game, player_id):
    """Discard a card."""
    card_id = int(self.request.get('c'))
    valid = game.Validate(player_id, 'DiscardPly', [card_id])
    if not valid:
      return {'errors': 'invalid move (is it your turn?)'}
    game.StopWaiting()
    game.Push('DiscardPly', [card_id])


class SelectCardHandler(webapp2.RequestHandler):
  @ply
  def post(self, game, player_id):
    """Select an element."""
    arg_id = self.request.get('c')
    if arg_id.isdigit():
      arg_id = int(arg_id)
    valid = game.Validate(player_id, 'SelectArg', [arg_id])
    if not valid:
      return {'errors': 'invalid move or selection'}
    game.FillWaitingArgs([arg_id])


class SelectHandler(webapp2.RequestHandler):
  """This is the pair to RequestSelection"""
  @ply
  def post(self, game, player_id):
    """Select an element."""
    option = int(self.request.get('o'))
    valid = game.Validate(player_id, 'Select', [option])
    if not valid:
      return {'errors': 'invalid move or selection'}
    game.FillWaitingArgs([option])


class SpendThreatHandler(webapp2.RequestHandler):
  @ply
  def post(self, game, player_id):
    position = self.request.get('p')
    valid = game.Validate(player_id, 'SpendThreatPly', [position])
    if not valid:
      return {'errors': 'invalid move (is it your turn?)'}
    game.StopWaiting()
    game.Push('SpendThreatPly', [position])


class StartOperationHandler(webapp2.RequestHandler):
  @ply
  def post(self, game, player_id):
    position = self.request.get('p')
    valid = game.Validate(player_id, 'StartOperationPly', [position])
    if not valid:
      return {'errors': 'invalid move (is it your turn?)'}
    game.StopWaiting()
    game.Push('StartOperationPly', [position])


class ScoreResolutionHandler(webapp2.RequestHandler):
  @ply
  def post(self, game, player_id):
    position = self.request.get('p')
    valid = game.Validate(player_id, 'ScoreResolutionPly', [position])
    if not valid:
      return {'errors': 'invalid move (is it your turn?)'}
    game.StopWaiting()
    game.Push('ScoreResolutionPly', [position])


class EquipHandler(webapp2.RequestHandler):
  @ply
  def post(self, game, player_id):
    item_id = int(self.request.get('i'))
    holder_id = int(self.request.get('h'))
    valid = game.Validate(player_id, 'EquipCardPly', [item_id, holder_id])
    if not valid:
      return {'errors': 'invalid move (is it your turn?)'}
    game.StopWaiting()
    game.Push('EquipCardPly', [item_id, holder_id])


class UnequipHandler(webapp2.RequestHandler):
  @ply
  def post(self, game, player_id):
    item_id = int(self.request.get('i'))
    valid = game.Validate(player_id, 'UnequipCardPly', [item_id])
    if not valid:
      return {'errors': 'invalid move (is it your turn?)'}
    game.StopWaiting()
    game.Push('UnequipCardPly', [item_id])


class AvertHandler(webapp2.RequestHandler):
  @ply
  def post(self, game, player_id):
    valid = game.Validate(player_id, 'PayAversionCost')
    card_ids = [int(c) for c in self.request.get_all('cs[]')]
    if not valid:
      return {'errors': 'Nothing to avert.'}
    game.Push('PayAversionCost', card_ids)


class DontAvertHandler(webapp2.RequestHandler):
  @ply
  def post(self, game, player_id):
    valid = game.Validate(player_id, 'DontAvertEffect')
    if not valid:
      return {'errors': 'Nothing to not avert.'}
    game.Push('DontAvertEffect')


class HomeHandler(webapp2.RequestHandler):
  def get(self):
    template = JINJA_ENVIRONMENT.get_template('templates/home.html')
    self.response.write(template.render())


ROUTES = [
  ('/', HomeHandler),
  ('/create', CreateRandomHandler),
  ('/(\d+)/create', CreateHandler),
  ('/(\d+)/delete', DeleteHandler),
  ('/(\d+)/stack', StackHandler),  #debug only
  ('/(\d+)/triggers', TriggersHandler),  #debug only
  ('/(\d+)/(1|2)', FrontendHandler),
  ('/(\d+)/(1|2)/json', JsonHandler),
  ('/(\d+)/(1|2)/changes', ChangesHandler),
  ('/(\d+)/(1|2)/end', EndTurnHandler),
  ('/(\d+)/(1|2)/move', MoveCardHandler),
  ('/(\d+)/(1|2)/draw', DrawCardHandler),
  ('/(\d+)/(1|2)/play', PlayCardHandler),
  ('/(\d+)/(1|2)/use', UseCardHandler),
  ('/(\d+)/(1|2)/mulligan', MulliganHandler),
  ('/(\d+)/(1|2)/discard', DiscardHandler),
  ('/(\d+)/(1)/operate', StartOperationHandler),
  ('/(\d+)/(1)/hidskill', HideoutSkillHandler),
  ('/(\d+)/(1)/equip', EquipHandler),
  ('/(\d+)/(1)/unequip', UnequipHandler),
  ('/(\d+)/(2)/offinf', OffInfHandler),
  ('/(\d+)/(2)/threat', SpendThreatHandler),
  ('/(\d+)/(2)/score', ScoreResolutionHandler),
  ('/(\d+)/(2)/pickres', ChooseResolutionHandler),
  ('/(\d+)/(1|2)/select', SelectCardHandler),
  ('/(\d+)/(1)/avert', AvertHandler),
  ('/(\d+)/(1)/sure', DontAvertHandler),
]


app = webapp2.WSGIApplication(routes=ROUTES, debug=True)
