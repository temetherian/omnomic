#!/usr/bin/python

import random

from google.appengine.ext import ndb

from cards import scenes
from cards import mob
from cards import pros
import engine


class Card(ndb.Model):
  card_id = ndb.IntegerProperty()
  db_id = ndb.IntegerProperty()  # For looking up images, i18n, etc.
  player = ndb.IntegerProperty()
  cost = ndb.IntegerProperty()
  card_type = ndb.StringProperty()
  holder = ndb.IntegerProperty()  # The card_id of the holder
  skill_cap = ndb.IntegerProperty(repeated=True)
  skill_points = ndb.IntegerProperty(repeated=True)
  unique = ndb.BooleanProperty()
  position = ndb.StringProperty()
  target_type = ndb.StringProperty()
  target_reqs = ndb.LocalStructuredProperty(engine.TargetReq, repeated=True)

  # Card abilities can exist when the card is created, and then their use validated.
  # Or they could be added as part of their play function.
  abilities = ndb.StringProperty(repeated=True)

  card_subtypes = ndb.StringProperty(repeated=True)
  is_faceup = ndb.BooleanProperty(default=False)
  play_function = ndb.StringProperty()
  counters = ndb.IntegerProperty()
  statuses = ndb.StringProperty(repeated=True)

  # ATTN
  # The best way to handle different cards may well be to subclass.
  # That would allow things like defining GetTargetForCard as a method
  # and overriding Change without monkey patching it.

  def Change(self, attr, value):
    prev_key = 'prev_' + attr
    prev_value = getattr(self, attr, None)
    setattr(self, attr, value)
    player_1_msg = self.VisibleInfo(1)
    player_2_msg = self.VisibleInfo(2)
    player_1_msg[prev_key] = player_2_msg[prev_key] = prev_value
    return engine.GameObjectChange(
        'card',
        self.card_id,
        attr,
        prev_value,
        value,
        {1: player_1_msg, 2: player_2_msg})

  def VisibleInfo(self, player_id):
    info = {'position': self.position,
            'player': self.player,
            'is_faceup': self.is_faceup,
            'card_id': self.card_id}
    if player_id == self.player or self.is_faceup or self.position.startswith('discard_'):
      info.update({'card_id': self.card_id,
                   'db_id': self.db_id,
                   'cost': self.cost,
                   'holder': self.holder,
                   'skill_cap': [i for i in self.skill_cap],
                   'skill_points': [i for i in self.skill_points],
                   'counters': self.counters,
                   'type': self.card_type,
                   'target_type': self.target_type,
                   'abilities': [str(a) for a in self.abilities],
                  })
    if self.player == 2 and self.position.startswith('scene_'):
      info.update({'cost': self.cost,
                   'type': self.card_type})
    return info

  def CanDiscoverCardsAt(self, position):
    return (self.position == position
            and self.card_type == 'operative'
            and not 'disabled' in self.statuses)


class Scene(ndb.Model):
  scene_id = ndb.IntegerProperty()
  db_id = ndb.IntegerProperty()
  tokens = ndb.StringProperty(repeated=True)
  influence = ndb.IntegerProperty(default=0)
  position = ndb.StringProperty()
  subtypes = ndb.StringProperty(repeated=True)

  # This is tiny bit of a hack, but in the current card set, it's only
  # possible for there to be 1 token attached, and so this saves us having
  # to make a OLJToken class.
  attached_token = ndb.StringProperty()

  def Change(self, attr, value):
    prev_key = 'prev_' + attr
    if attr in ('subtypes', 'tokens'):
      # Repeated StringProperties sometimes come out as _BaseValues which can't be
      # serialized into JSON by default. So this pattern is a kludge around that.
      prev_value = [str(i) for i in getattr(self, attr, [])]
    else:
      prev_value = getattr(self, attr, None)
    setattr(self, attr, value)
    message = self.to_dict()
    message['subtypes'] = [str(i) for i in self.subtypes]
    message['tokens'] = [str(i) for i in self.tokens]
    message[prev_key] = prev_value

    # The Crew (player 1) doesn't know which resolution is in the scene.
    player_1_msg = message.copy()  # n.b.: This is just a shallow copy.
    player_1_msg['tokens'] = [('R_' if t[0] == 'R' else t) for t in message['tokens']]
    if attr == 'tokens':
      player_1_msg['prev_tokens'] = [('R_' if t[0] == 'R' else t) for t in message['prev_tokens']]

    _, message['inf_req'] = self.GetResolutionInfo()

    return engine.GameObjectChange(
        'scene',
        self.scene_id,
        attr,
        prev_value,
        value,
        {1: player_1_msg, 2: message})

  def VisibleInfo(self, player_id):
    info = self.to_dict()
    info['tokens'] = []
    for t in self.tokens:
      if t[0] == 'R':
        if player_id == 1:
          info['tokens'].append('R_')
        else:
          info['tokens'].append(t)
          if t[1] == '2': info['inf_req'] = 5
          if t[1] == '3': info['inf_req'] = 6
          if t[1] == '4': info['inf_req'] = 7
      else:
        info['tokens'].append(t)
    return info

  def GetResolutionInfo(self):
    for t in self.tokens:
      if t[0] == 'R':
        if t[1] == '2': inf_req = 5
        if t[1] == '3': inf_req = 6
        if t[1] == '4': inf_req = 7
        return t, inf_req
    return None, None


class Office(ndb.Model):
  position = 'office'
  influence = ndb.IntegerProperty(default=0)
  subtypes = ['private']

  def Change(self, attr, value):
    prev_key = 'prev_' + attr
    prev_value = getattr(self, attr, None)
    setattr(self, attr, value)
    message = self.to_dict()
    # Repeated StringProperties sometimes come out as _BaseValues which can't be
    # serialized into JSON by default. So this is a kludge around that.
    message['subtypes'] = [str(i) for i in self.subtypes]
    message[prev_key] = prev_value
    return engine.GameObjectChange(
        'office',
        0,
        attr,
        prev_value,
        value,
        {1: message, 2: message})


class OneLastJobGame(engine.Game, mob.MobCards, pros.ProsCards):
  CREW = 1
  POWERS = 2

  STARTING_HAND_SIZE = 5
  WINNING_SCORE = 10
  NUMBER_OF_LOCATIONS = 3
  ACTIVE_POSITIONS = ('scene_0', 'scene_1', 'scene_2', 'office', 'hideout')

  # This could be player-specific
  WAIT_FOR_ACTION = ('WaitForAction', [], ['__awaiting_input'])

  crew_deck = ndb.IntegerProperty(repeated=True, indexed=False)
  powers_deck = ndb.IntegerProperty(repeated=True, indexed=False)
  scene_deck = ndb.IntegerProperty(repeated=True, indexed=False)
  resolution_deck = ndb.StringProperty(repeated=True, indexed=False)
  cards = ndb.LocalStructuredProperty(Card, repeated=True)
  scenes = ndb.LocalStructuredProperty(Scene, repeated=True)
  office = ndb.LocalStructuredProperty(Office, indexed=False)
  crew_points = ndb.IntegerProperty(default=0, indexed=False)
  powers_points = ndb.IntegerProperty(default=0, indexed=False)
  acting_player = ndb.IntegerProperty(default=0, indexed=False)
  acting_player_actions = ndb.IntegerProperty(default=0, indexed=False)
  threat_level = ndb.IntegerProperty(default=0, indexed=False)
  max_crew_hand_size = ndb.IntegerProperty(default=5, indexed=False)
  max_powers_hand_size = ndb.IntegerProperty(default=5, indexed=False)

  # Network stuff. Would be nice to separate this.
  crew_channel_id = ndb.StringProperty(indexed=False)
  powers_channel_id = ndb.StringProperty(indexed=False)

  def Validate(self, player_id, function, args=None):
    """Check if received play is valid."""
    expected_player = self.acting_player
    for tag in self.stack[-1].tags:
      if tag.startswith('__waiting_on:'):
        expected_player = int(tag.split(':')[1])
    if player_id != expected_player:  # TODO: use a token
      return False
    # The __awaiting_input item could hold a validator in it.
    # For now we'll do things more manually.
    if 'AcceptPly' == self.stack[-1].function:
      # TODO: This particular restriction is probably common enough to move into the engine.
      allowed_functions = self.stack[-1].args
      return function in allowed_functions
    if ('avertable' in self.stack[-1].tags) != (function in ('PayAversionCost', 'DontAvertEffect')):
      return False
    if ('reschoice' in self.stack[-1].tags) != (function == 'ChooseResolution'):
      return False
    if 'SelectArg' == function:
       if not args or '__awaiting_input' not in self.stack[-1].tags:
         return False
       allowed_args = self.stack[-1].args
       return args[0] in allowed_args
       # TODO: better variadic support
    if 'Select' == function:
      if not args or self.stack[-1].function != 'RequestSelection':
        return False
      allowed_args = self.stack[-1].args
      return args[0] in allowed_args
    return True

  def InitializeGame(self):
    """Setup the initial game state."""
    win_trigger = engine.Trigger(
        object_class='Game',
        matcher='CheckForWin',
        function='Win')

    self.reactive_triggers = [win_trigger]

    self.crew_deck = [c.card_id for c in self.cards if c.player == self.CREW]
    self.powers_deck = [c.card_id for c in self.cards if c.player == self.POWERS and 'boss' not in c.card_subtypes]
    self.office = Office()
    self.resolution_deck = ['R2'] * 3 + ['R3'] * 4 + ['R4'] * 3
    random.shuffle(self.resolution_deck)
    for i, scene_dict in enumerate(scenes.MANSION):
      scene_id = i
      self.scenes.append(
          Scene(scene_id=scene_id,
                db_id=scene_dict['db_id'],
                tokens=scene_dict['tokens'],
                subtypes=scene_dict['subtypes'],
                position='scene_deck')
      )
      reactive_triggers = scene_dict.get('reactive_triggers', [])
      for matcher, function in reactive_triggers:
        new_trigger = engine.Trigger(
            object_class='scene',
            object_id=scene_id,
            matcher=matcher,
            function=function)
        self.reactive_triggers.append(new_trigger)
      self.scene_deck.append(scene_id)

    random.shuffle(self.crew_deck)
    random.shuffle(self.powers_deck)
    random.shuffle(self.scene_deck)
    for _ in xrange(self.STARTING_HAND_SIZE):
      self.DrawCard(self.CREW)
      self.DrawCard(self.POWERS)
    self.Mulligans()
    self.ProcessStack()
    self.Save()

  def GlobalStates(self):
    """Provide globally known state information with every change."""
    state = super(OneLastJobGame, self).GlobalStates()

    # This information can actually be derived from the change information sent,
    # but it is sometimes convenient to make life easier on the client's coder.
    state['acting_player'] = self.acting_player
    state['crew_deck_size'] = len(self.crew_deck)
    state['powers_deck_size'] = len(self.powers_deck)
    # state['office_influence'] = self.office.influence
    # state['threat_level'] = self.threat_level
    return state

  def PlayerStates(self, player_id):
    """Sent with every message to the player."""
    hand_name = 'crew_hand' if player_id == self.CREW else 'powers_hand'
    state = {'targets': {}}
    for card in self.cards:
      if card.position == hand_name and card.target_type:
        state['targets'][card.card_id] = self.GetTargetsForCard(card.card_id)
    if self.acting_player == player_id and self.stack[-1].function == 'RequestSelection':
      state['select_options'] = self.stack[-1].args
      for t in self.stack[-1].tags:
        if t.startswith('type:'):
          state['select_type'] = t.split(':')[1]
    if not self.stack:
      return state
    if 'avertable' in self.stack[-1].tags:
      # TODO: be more generic about __awaiting_input items
      state['aversion_location'] = self.stack[-1].args[0]
      for tag in self.stack[-1].tags:
        if tag.startswith('aversioncost:'):
          state['aversion_cost'] = tag.split(':')[1]
      owner_class = self.stack[-1].owner_class
      state['aversion_owner_class'] = owner_class

      # perhaps this lookup burden should be on the client?
      if owner_class == 'card':
        db_id = self.GetCardById(self.stack[-1].owner_id).db_id
      else:
        db_id = self.stack[-1].owner_id
      state['aversion_owner_db_id'] = db_id
    if player_id == self.POWERS and 'reschoice' in self.stack[-1].tags:
      state['resolution_options'] = self.stack[-1].args
      for tag in self.stack[-1].tags:
        if tag.startswith('db_id:'):
          state['scene_db_id'] = tag.split(':')[1]
        if tag.startswith('position:'):
          state['position'] = tag.split(':')[1]
    return state

  ###########
  # Helpers #
  ###########

  def GetCardById(self, card_id):
    for card in self.cards:
      if card.card_id == card_id:
        return card

  def GetSceneById(self, scene_id):
    for l in self.scenes:
      if l.scene_id == scene_id:
        return l

  def GetSceneByPosition(self, position):
    for l in self.scenes:
      if l.position == position:
        return l

  def GetLoomingComplicationAt(self, position):
    for card in self.cards:
      if (card.position == position
          and card.card_type == 'complication'
          and not card.is_faceup):
        return card

  def GetPlayerHand(self, player):
    hand_name = 'crew_hand' if player == self.CREW else 'powers_hand'
    return [c.card_id for c in self.cards if c.position == hand_name]

  def GetTargetsForCard(self, card_id):
    """Provide a list of targets for playing a card.

    This is one approach for getting a ply from a player involving multiple choices.
    Note that this approach requires precomputing the options for each choice the
    player could make.

    Other approaches include:
    (a) coding a smarter client, that's more aware of the rules of your game
        (e.g. how the OLJ client knows which cards can pay aversion costs)
    (b) computing options for the player only when they're needed
        (e.g. how a target is requested in HideoutSkillPly)

    Ultimately, there are trade-offs between programmer time, server time,
    payload size, and round trips.
    """
    card = self.GetCardById(card_id)
    targets = []
    if card.target_type.startswith('scene'):
      for candidate in self.scenes:
        if candidate.position not in ('scene_0', 'scene_1', 'scene_2'):
          continue
        for req in card.target_reqs:
          value = getattr(candidate, req.attr)
          if req.e_value != value and req.e_value not in value:
            break
        else:
          if card.target_type == 'scene':
            targets.append(candidate.scene_id)
          if card.target_type == 'scene_position':
            targets.append(candidate.position)
    if card.target_type == 'card':
      for candidate in self.cards:
        if candidate.position not in self.ACTIVE_POSITIONS:
          continue
        for req in card.target_reqs:
          value = getattr(candidate, req.attr)
          if req.e_value != value and req.e_value not in value:
            break
        else:
          targets.append(candidate.card_id)
    return targets

  def IsOperativeFull(self, card_id):
    for card in self.cards:
      if card.card_type == 'item' and card.holder == card_id:
        return True
    return False

  ######################################
  # Turn definition                    #
  #                                    #
  #   ScenePhase                       #
  #   PowersTurn                       #
  #     StartOfPowersTurn: draw        #
  #     PowersActions                  #
  #     EndOfPowersTurn: discard       #
  #   CrewTurn                         #
  #     StartOfCrewTurn: draw          #
  #     CrewActions                    #
  #     EndOfCrewTurn: discard         #
  ######################################

  def Mulligans(self):
    self.Do([('PowersMulligan',),
             ('CrewMulligan',),
             ('TurnSetup',)])

  def PowersMulligan(self):
    self.acting_player = self.POWERS
    self.Push('AcceptPly', ['MulliganPly'], ['__awaiting_input', '__waiting_on:2'])

  def CrewMulligan(self):
    self.acting_player = self.CREW
    self.Push('AcceptPly', ['MulliganPly'], ['__awaiting_input', '__waiting_on:1'])

  def TurnSetup(self):
    self.Do([('ScenePhase',),
             ('PowersTurn',),
             ('CrewTurn',),
             ('TurnSetup',)])

  def ScenePhase(self):
    self.acting_player = self.POWERS
    self.Do([('MaybeAddScene',),
             ('ClearResolvedScenes',),
            ])

  def MaybeAddScene(self):
    filled = set()
    for s in self.scenes:
      filled.add(s.position)
    for pos in ('scene_1', 'scene_2', 'scene_0'):
      if pos not in filled:
        self.Push('NewScene', [pos])
        break

  def ClearResolvedScenes(self):
    changes = []
    for s in self.scenes:
      if s.position in ('scene_0', 'scene_1', 'scene_2'):
        for t in s.tokens:
          if t[0] == 'R':
            break
        else:
          self.Push('ClearScene', [s.position])

  def PowersTurn(self):
    self.acting_player = self.POWERS
    self.acting_player_actions = 5
    self.Do([('StartOfPowersTurn',),
             ('PowersActions',),
             ('EndOfPowersTurn',)])
    return [engine.GlobalChange('acting_player_actions',
                                self.acting_player_actions)]

  def StartOfPowersTurn(self):
    self.Push('DrawCard', [self.POWERS])

  def PowersActions(self):
    self.Push(*self.WAIT_FOR_ACTION)

  def EndOfPowersTurn(self):
    self.Push('PowersDiscard')

  def PowersDiscard(self):
    if len(self.GetPlayerHand(self.POWERS)) > self.max_powers_hand_size:
      self.Do([('AcceptPly', ['DiscardPly'], ['__awaiting_input', '__waiting_on:2']),
               ('PowersDiscard',)])

  def CrewTurn(self):
    self.acting_player = self.CREW
    self.acting_player_actions = 5
    self.Do([('StartOfCrewTurn',),
             ('CrewActions',),
             ('EndOfCrewTurn',)])
    return [engine.GlobalChange('acting_player_actions',
                                self.acting_player_actions)]

  def StartOfCrewTurn(self):
    self.Push('DrawCard', [self.CREW])

  def CrewActions(self):
    self.Push(*self.WAIT_FOR_ACTION)

  def EndOfCrewTurn(self):
    self.Push('CrewDiscard')

  def CrewDiscard(self):
    if len(self.GetPlayerHand(self.CREW)) > self.max_crew_hand_size:
      self.Do([('AcceptPly', ['DiscardPly'], ['__awaiting_input', '__waiting_on:1']),
               ('CrewDiscard',)])

  ####################################################
  # Plies                                            #
  #                                                  #
  # The game itself should likely not trigger these. #
  ####################################################

  # TODO: There needs to be some checking to make sure these plies came from the
  #       active player.

  def EndTurn(self):
    """Ends the player's turn by not requesting further actions."""
    pass

  def MulliganPly(self, player_id, *card_ids):
    if player_id == self.CREW:
      deck = self.crew_deck
      player_str = 'crew'
    elif player_id == self.POWERS:
      deck = self.powers_deck
      player_str = 'powers'
    hand_name = '%s_hand' % player_str
    deck_name = '%s_deck' % player_str

    changes = []
    cards = []
    for card_id in card_ids:
      card = self.GetCardById(card_id)
      if card.position != hand_name:
        return [engine.GameWarning('illegal play')]
      cards.append(card)

    for _ in xrange(len(card_ids)):
      self.Push('DrawCard', [player_id])

    for card in cards:
      deck.append(card.card_id)
      changes.append(card.Change('position', deck_name))

    random.shuffle(deck)

    return changes

  def MoveCardPly(self, card_id, new_position):
    # Probably needs more validation.
    if self.acting_player_actions < 1:
      self.Push(*self.WAIT_FOR_ACTION)
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    card = self.GetCardById(card_id)
    if new_position.startswith('scene'):
      if not self.GetSceneByPosition(new_position):
        self.Push(*self.WAIT_FOR_ACTION)
        return [engine.PlayerWarning(self.acting_player, "There isn't a scene at that position.")]
    if card.card_type not in ('actor', 'operative'):
      self.Push(*self.WAIT_FOR_ACTION)
      return [engine.PlayerWarning(self.acting_player, "That card type cannot be moved.")]
    self.acting_player_actions -= 1
    self.Do([
        ('MoveCard', [card_id, new_position]),
        self.WAIT_FOR_ACTION
    ])
    return [engine.GlobalChange('acting_player_actions',
                                self.acting_player_actions)]

  def EquipCardPly(self, item_id, holder_id):
    if self.acting_player != self.CREW:
      self.Push(*self.WAIT_FOR_ACTION)
      return [engine.PlayerWarning(self.acting_player, "It's not your turn.")]
    item = self.GetCardById(item_id)
    if (item.card_type != 'item' or (item.position not in self.ACTIVE_POSITIONS)):
      self.Push(*self.WAIT_FOR_ACTION)
      return [engine.PlayerWarning(self.acting_player, 'This card cannot be equipped.')]

    # Special case for Whisper Earrings
    # TODO: Create Validators and use those instead.
    if item.db_id == 14 and item.position != 'hideout' and item.holder:
      self.Push(*self.WAIT_FOR_ACTION)
      return [engine.PlayerWarning(self.acting_player, 'Whisper Earrings cannot be unequipped here.')]

    holder = self.GetCardById(holder_id)
    if holder.card_type != 'operative':
      self.Push(*self.WAIT_FOR_ACTION)
      return [engine.PlayerWarning(self.acting_player, 'Only operatives can carry items.')]
    if item.position != holder.position:
      self.Push(*self.WAIT_FOR_ACTION)
      return [engine.PlayerWarning(self.acting_player, "That operative isn't there to pick this up.")]
    if self.IsOperativeFull(holder_id):
      self.Push(*self.WAIT_FOR_ACTION)
      return [engine.PlayerWarning(self.acting_player, "That operative is already holding something.")]
    self.Do([
        ('AttachToCard', [item_id, holder_id]),
        self.WAIT_FOR_ACTION
    ])
    return []

  def UnequipCardPly(self, item_id):
    if self.acting_player != self.CREW:
      self.Push(*self.WAIT_FOR_ACTION)
      return [engine.PlayerWarning(self.acting_player, "It's not your turn.")]
    item = self.GetCardById(item_id)
    if (item.card_type != 'item' or (item.position not in self.ACTIVE_POSITIONS)):
      self.Push(*self.WAIT_FOR_ACTION)
      return [engine.PlayerWarning(self.acting_player, "That doesn't even make sense.")]
    # Special case for Whisper Earrings; TODO: as above
    if item.db_id == 14 and item.position != 'hideout':
      self.Push(*self.WAIT_FOR_ACTION)
      return [engine.PlayerWarning(self.acting_player, 'Whisper Earrings cannot be unequipped here.')]
    self.Do([
        ('DropCard', [item_id]),
        self.WAIT_FOR_ACTION
    ])
    return []

  def SpendThreatPly(self, position):
    if (self.acting_player_actions < 1
        or self.threat_level < 1
        or self.acting_player != self.POWERS
        or not position.startswith('scene')):
      self.Push(*self.WAIT_FOR_ACTION)
      return [engine.PlayerWarning(self.acting_player, "You can't do that.")]
    scene = self.GetSceneByPosition(position)
    self.acting_player_actions -= 1
    self.Do([
        ('LowerThreat1',),
        ('AddSnagToScene', [scene.scene_id]),
        self.WAIT_FOR_ACTION,
    ])
    return [engine.GlobalChange('acting_player_actions', self.acting_player_actions)]

  def ScoreResolutionPly(self, position):
    if self.acting_player != self.POWERS or not position.startswith('scene'):
      self.Push(*self.WAIT_FOR_ACTION)
      return [engine.PlayerWarning(self.acting_player, "You can't do that.")]
    scene = self.GetSceneByPosition(position)
    resolution, inf_req = scene.GetResolutionInfo()
    if scene.influence < inf_req:
      self.Push(*self.WAIT_FOR_ACTION)
      return [engine.PlayerWarning(self.POWERS, "There's not enough influence there yet.")]
    tokens_here = scene.tokens[:]  # copy
    tokens_here.remove(resolution)
    points = int(resolution[1])
    self.Do([
        ('Score', [self.POWERS, points]),
        self.WAIT_FOR_ACTION,
    ])
    return [scene.Change('tokens', tokens_here),
            scene.Change('influence', 0)]

  def DrawCardPly(self):
    # Probably needs more validation.
    if self.acting_player_actions < 1:
      self.Push(*self.WAIT_FOR_ACTION)
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    self.acting_player_actions -= 1
    self.Do([
        ('DrawCard', [self.acting_player]),
        self.WAIT_FOR_ACTION
    ])
    return [engine.GlobalChange('acting_player_actions',
                                self.acting_player_actions)]

  def PlayCardPly(self, card_id, target=None):
    # Needs more validation.
    if target is None:
      play_args = [card_id]
    else:
      if target.isdigit():
        target = int(target)
      play_args = [card_id, target]
    hand_name = 'crew_hand' if self.acting_player == self.CREW else 'powers_hand'
    card = self.GetCardById(card_id)

    illegal_reason = None
    if card.position != hand_name:
      illegal_reason = "That card isn't in your hand."
    if self.acting_player_actions < card.cost:
      illegal_reason = "You don't have enough actions to play that card"
    if card.unique:
      for c in self.cards:
        if c.db_id == card.db_id and c.position in self.ACTIVE_POSITIONS:
          illegal = "There's already a copy of that card in play."
          break

    if illegal_reason:
      self.Push(*self.WAIT_FOR_ACTION)
      return [engine.PlayerWarning(self.acting_player, illegal_reason)]

    # This needed to move into the play function so cards can verify that
    # they're playable before the cost is paid.
    # self.acting_player_actions -= card.cost  # This could go on the stack.
    self.Do([
        (card.play_function, play_args),
        self.WAIT_FOR_ACTION
    ])
    return [engine.GlobalChange('acting_player_actions',
                                self.acting_player_actions)]

  def UseCardPly(self, card_id, ability):
    card = self.GetCardById(card_id)
    if ability not in card.abilities:
      self.Push(*self.WAIT_FOR_ACTION)
      return [engine.PlayerWarning(self.acting_player, "I wasn't aware that was something that that card could do.")]
    self.Do([
        (ability, [card_id], [], 'card', card_id),
        self.WAIT_FOR_ACTION
    ])

  def DiscardPly(self, card_id):
    hand_name = 'crew_hand' if self.acting_player == self.CREW else 'powers_hand'
    card = self.GetCardById(card_id)
    if card.position != hand_name:
      return [engine.PlayerWarning(self.acting_player, "You can't discard a card that isn't in your hand.")]
    # If we make "when discarded" triggers, a Discard action could be helpful.
    return [card.Change('position', 'discard_%s' % self.acting_player)]

  def OfficeInfluencePly(self):
    if self.acting_player_actions < 1 or self.acting_player != self.POWERS:
      self.Push(*self.WAIT_FOR_ACTION)
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    self.acting_player_actions -= 1
    self.Do([
        ('AddInfluenceToOffice', [1]),
        self.WAIT_FOR_ACTION
    ])
    return [engine.GlobalChange('acting_player_actions',
                                self.acting_player_actions)]

  def HideoutSkillPly(self):
    if self.acting_player_actions < 1 or self.acting_player != self.CREW:
      self.Push(*self.WAIT_FOR_ACTION)
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    valid_targets = []
    for card in self.cards:
      if card.position == 'hideout':
        if card.skill_cap:
          if card.skill_points[0] < card.skill_cap[0] or card.skill_points[1] < card.skill_cap[1]:
            valid_targets.append(card.card_id)
    if not valid_targets:
      self.Push(*self.WAIT_FOR_ACTION)
      return [engine.PlayerWarning(self.acting_player, "There's nobody there who needs it.")]
    self.Do([
        ('AddHideoutSkillToCard', valid_targets, ['__awaiting_input', '__waiting_on:1']),
        self.WAIT_FOR_ACTION
    ])

  def StartOperationPly(self, position):
    if self.acting_player_actions < 1 or self.acting_player != self.CREW or not position.startswith('scene'):
      self.Push(*self.WAIT_FOR_ACTION)
      return [engine.PlayerWarning(self.acting_player, "You can't do that.")]
    for card in self.cards:
      if card.CanDiscoverCardsAt(position):
        self.acting_player_actions -= 1
        self.Do([
            ('StartOperation', [position]),
            self.WAIT_FOR_ACTION
        ])
        return [engine.GlobalChange('acting_player_actions',
                                    self.acting_player_actions)]
    self.Push(*self.WAIT_FOR_ACTION)
    return [engine.PlayerWarning(self.CREW, "There's nobody there to do start the operation.")]


  #############################################################################
  # Matchers
  #
  # Args:
  #   object_class: the object class of the matcher's owner
  #   object_id: the ID of the matcher's owner
  #   stack_item: the StackItem that's being checked against the matcher
  # Returns:
  #   (bool) Whether the StackItem matched
  #   (list or None) A list of arguments to pass to the triggered function
  #############################################################################

  def CheckForWin(self, unused_class, unused_id, stack_item, changes):
    if stack_item.function != 'Score':
      return False, None
    if self.crew_points >= self.WINNING_SCORE:
      return True, [self.CREW]
    elif self.powers_points >= self.WINNING_SCORE:
      return True, [self.POWERS]
    return False, None

  def WhenCrewScores(self, unused_class, object_id, stack_item, changes):
    if stack_item.function != 'Score':
      return False, None
    if stack_item.args[0] == self.CREW:
      return True, [object_id]
    return False, None

  def StartOfOperationAnywhere(self, object_class, object_id, stack_item, changes):
    if stack_item.function != 'StartOfOperation':
      return False, None
    return True, [stack_item.args[0]]

  def EndOfOperationAnywhere(self, object_class, object_id, stack_item, changes):
    if stack_item.function != 'EndOfOperation':
      return False, None
    return True, [stack_item.args[0]]

  def EndOfOperationAtScene(self, object_class, object_id, stack_item, changes):
    if stack_item.function != 'EndOfOperation':
      return False, None
    scene = self.GetSceneByPosition(stack_item.args[0])
    return True, [scene.scene_id]

  def StartOfOperationHere(self, object_class, object_id, stack_item, changes):
    if stack_item.function != 'StartOfOperation':
      return False, None
    # TODO: generalize this object_class thing
    if object_class == 'scene':
      this_scene = self.GetSceneById(object_id)
      here = this_scene.position
    if object_class == 'card':
      this_card = self.GetCardById(object_id)
      if not this_card.is_faceup:
        # Don't resolve StartOfOperationHere triggers on facedown complications.
        # Actors will already be faceup.
        return False, None
      here = this_card.position
    if stack_item.args[0] == here:
      return True, [here]
    return False, None

  def EndOfOperationHere(self, object_class, object_id, stack_item, changes):
    if stack_item.function != 'EndOfOperation':
      return False, None
    # TODO: generalize this object_class thing
    if object_class == 'scene':
      this_scene = self.GetSceneById(object_id)
      here = this_scene.position
    if object_class == 'card':
      this_card = self.GetCardById(object_id)
      if not this_card.is_faceup:
        return False, None
      here = this_card.position
    if stack_item.args[0] == here:
      return True, [here]
    return False, None

  def OnSearchScene(self, object_class, object_id, stack_item, changes):
    if stack_item.function == 'SearchScene':
      here = stack_item.args[0]
      return True, [here]
    return False, None

  def OnEndOfOperation(self, object_class, object_id, stack_item, changes):
    if stack_item.function == 'EndOfOperation':
      here = stack_item.args[0]
      return True, [here]
    return False, None

  def OnStartOfCrewTurn(self, object_class, object_id, stack_item, changes):
    if stack_item.function == 'StartOfCrewTurn':
      return True, [object_id]
    return False, None

  def OnEndOfCrewTurn(self, object_class, object_id, stack_item, changes):
    if stack_item.function == 'EndOfCrewTurn':
      return True, [object_id]
    return False, None

  def OnStartOfPowersTurn(self, object_class, object_id, stack_item, changes):
    if stack_item.function == 'StartOfPowersTurn':
      return True, [object_id]
    return False, None

  def OnEndOfPowersTurn(self, object_class, object_id, stack_item, changes):
    if stack_item.function == 'EndOfPowersTurn':
      return True, [object_id]
    return False, None

  def ThisCardsHolderMoved(self, object_class, object_id, stack_item, changes):
    if stack_item.function not in ('MoveCard', 'TrashCard'):
      return False, None
    if object_class == 'card':
      this_card = self.GetCardById(object_id)
      if stack_item.args[0] == this_card.holder:
        return True, [object_id, changes[0].prev, changes[0].new]
    return False, None

  def ThisCardUnattached(self, object_class, object_id, unused_stack_item, changes):
    if object_class == 'card' and not self.GetCardById(object_id).holder:
      return True, None
    return False, None

  def ThisCardOutOfPlay(self, object_class, object_id, unused_stack_item, changes):
    if object_class == 'card' and not self.GetCardById(object_id).position in self.ACTIVE_POSITIONS:
      return True, None
    return False, None

  def ThisCardsSceneMoved(self, object_class, object_id, stack_item, changes):
    if stack_item.function != 'MoveScene':
      return False, None
    if object_class == 'card':
      card = self.GetCardById(object_id)
      if changes[0].prev == card.position:
        return True, [object_id, changes[0].prev, changes[0].new]
    return False, None

  def WhenDiscovered(self, object_class, object_id, stack_item, changes):
    if stack_item.function != 'DiscoverCardAt':
      return False, None
    discovered_card, position = stack_item.args
    if object_class == 'card' and object_id == discovered_card:
      return True, [discovered_card, position]
    return False, None

  ################
  # Game actions #
  ################

  def MoveCard(self, card_id, new_position):
    card = self.GetCardById(card_id)
    change = card.Change('position', new_position)
    return [change]

  def TrashCard(self, card_id):
    card = self.GetCardById(card_id)
    change = card.Change('position', 'discard_%s' % card.player)
    if card.holder:
      change = card.Change('holder', 0)
    return [change]

  def DrawCard(self, player_id):
    if player_id == self.CREW:
      deck = self.crew_deck
      hand_name = 'crew_hand'
    elif player_id == self.POWERS:
      deck = self.powers_deck
      hand_name = 'powers_hand'

    if len(deck) == 0:
      return [engine.PlayerWarning(self.acting_player, "You don't have any cards left to draw.")]
    else:
      drawn_card_id = deck.pop()
      card = self.GetCardById(drawn_card_id)
      change = card.Change('position', hand_name)
      return [change]

  def NewScene(self, position):
    drawn_scene_id = self.scene_deck.pop()
    scene = self.GetSceneById(drawn_scene_id)
    change = scene.Change('position', position)
    options = self.resolution_deck[0:2]
    self.Do([
        ('ChooseResolution', options, ['__awaiting_input',
                                       '__waiting_on:2',
                                       'reschoice',
                                       'position:%s' % position,
                                       'db_id:%s' % scene.db_id]),
        ('AddResolutionToScene', [drawn_scene_id, ''], ['__awaiting_input']),
    ])
    return [change]

  def ChooseResolution(self, resolution):
    # This is the sort of thing I want to make more generic.
    if self.stack[-1].function != 'AddResolutionToScene':
      return [engine.GameWarning('Something went wrong: expected AddResolutionToScene')]
    self.stack[-1].args[1] = resolution
    self.stack[-1].tags.remove('__awaiting_input')

  def AddResolutionToScene(self, scene_id, resolution):
    scene = self.GetSceneById(scene_id)
    options, leftover = self.resolution_deck[0:2], self.resolution_deck[2:]
    if resolution not in options:
      self.Do([
          ('ChooseResolution', options, ['__awaiting_input',
                                         '__waiting_on:2',
                                         'reschoice',
                                         'position:%s' % scene.position,
                                         'db_id:%s' % scene.db_id]),
          ('AddResolutionToScene', [scene_id, ''], ['__awaiting_input']),
      ])
      return [engine.GameWarning('Invalid selection.')]
    options.remove(resolution)
    self.resolution_deck = leftover + options
    return [scene.Change('tokens', scene.tokens + [resolution])]

  def AddHideoutSkillToCard(self, card_id):
    # TODO: separate into Guards and Locks
    card = self.GetCardById(card_id)
    if (self.acting_player_actions < 1 or
        not card.skill_cap or
        not card.position == 'hideout'):
      return [engine.PlayerWarning(self.acting_player, "You can't do that.")]
    if card.skill_points[0] < card.skill_cap[0]:
      change = card.Change('skill_points', [card.skill_points[0] + 1, card.skill_points[1]])
      self.acting_player_actions -= 1
      return [engine.GlobalChange('acting_player_actions', self.acting_player_actions),
              change]
    elif card.skill_points[1] < card.skill_cap[1]:
      change = card.Change('skill_points', [card.skill_points[0], card.skill_points[1] + 1])
      self.acting_player_actions -= 1
      return [engine.GlobalChange('acting_player_actions', self.acting_player_actions),
              change]
    else:
      return [engine.PlayerWarning(self.acting_player, "You can't do that.")]

  def Add1SkillToCardIfAble(self, card_id):
    card = self.GetCardById(card_id)
    if card.skill_points[0] < card.skill_cap[0]:
      change = card.Change('skill_points', [card.skill_points[0] + 1, card.skill_points[1]])
      return [change]
    elif card.skill_points[1] < card.skill_cap[1]:
      change = card.Change('skill_points', [card.skill_points[0], card.skill_points[1] + 1])
      return [change]

  def AddInfluenceToScene(self, scene_id, n):
    scene = self.GetSceneById(scene_id)
    change = scene.Change('influence', scene.influence + n)
    return [change]

  def AddInfluenceToOffice(self, n):
    office = self.office
    change = office.Change('influence', office.influence + n)
    return [change]

  def Move1InfluenceHere(self, card_id):
    card = self.GetCardById(card_id)
    if (self.acting_player_actions < 1 or
        self.office.influence < 1 or
        not card.position.startswith('scene_')):
      return [engine.PlayerWarning(self.acting_player, "You can't do that.")]
    self.acting_player_actions -= 1
    scene = self.GetSceneByPosition(card.position)
    change_1 = self.office.Change('influence', self.office.influence - 1)
    change_2 = scene.Change('influence', scene.influence + 1)
    return [engine.GlobalChange('acting_player_actions', self.acting_player_actions),
            change_1, change_2]

  def RaiseThreat1(self, *unused_args):
    if self.threat_level < 5:
      self.threat_level += 1
      return [engine.GlobalChange('threat_level', self.threat_level)]

  def LowerThreat1(self):
    if self.threat_level > 0:
      self.threat_level -= 1
      return [engine.GlobalChange('threat_level', self.threat_level)]

  def ClearScene(self, position):
    scene = self.GetSceneByPosition(position)
    self.Do([
      ('MoveScene', [scene.scene_id, 'scene_discard']),
      ('MoveOperativesHome', [position]),
      ('MovePowersCardsHome', [position]),
      ('TrashAbandonedItems', [position]),
      ])
    return []

  def MoveScene(self, scene_id, position):
    scene = self.GetSceneById(scene_id)
    return [scene.Change('position', position)]

  def MoveOperativesHome(self, position):
    for card in self.cards:
      if (card.position == position
          and card.player == self.CREW
          and card.card_type == 'operative'):
        self.Push('MoveCard', [card.card_id, 'hideout'])

  def MovePowersCardsHome(self, position):
    for card in self.cards:
      if card.position == position and card.player == self.POWERS:
        if card.card_type == 'complication' and not card.is_faceup:
          self.Push('MoveCard', [card.card_id, 'powers_hand'])
        elif card.card_type == 'actor':
          self.Push('MoveCard', [card.card_id, 'office'])

  def TrashAbandonedItems(self, position):
    for card in self.cards:
      if (card.position == position
          and card.player == self.CREW
          and card.card_type == 'item'):
        self.Push('TrashCard', [card_id])

  def Score(self, player_id, points):
    if player_id == self.CREW:
      self.crew_points += points
      return [engine.GlobalChange('crew_points', self.crew_points)]
    elif player_id == self.POWERS:
      self.powers_points += points
      return [engine.GlobalChange('powers_points', self.powers_points)]

  def Win(self, winner):
    self.acting_player = 0
    self.stack = []
    name = 'The Crew' if winner == self.CREW else 'The Powers'
    return [engine.GlobalMessage('%s have won the game.' % name),
            engine.GlobalChange('winner', winner),
            engine.GlobalChange('acting_player', self.acting_player)]

  def PlaceInHideout(self, card_id):
    card = self.GetCardById(card_id)
    if self.acting_player_actions < card.cost:
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    self.acting_player_actions -= card.cost
    placement = card.Change('position', 'hideout')
    reveal = card.Change('is_faceup', True)
    changes = [engine.GlobalChange('acting_player_actions', self.acting_player_actions),
               placement,
               reveal]
    if card.skill_cap:
      skill = card.Change('skill_points', [0, 0])
      changes.append(skill)
    return changes

  def PlaceInOffice(self, card_id):
    card = self.GetCardById(card_id)
    if self.acting_player_actions < card.cost:
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    self.acting_player_actions -= card.cost
    placement = card.Change('position', 'office')
    reveal = card.Change('is_faceup', True)
    return [engine.GlobalChange('acting_player_actions', self.acting_player_actions),
            placement,
            reveal]

  def PlaceInSceneFacedown(self, card_id, position):
    card = self.GetCardById(card_id)
    if self.acting_player_actions < card.cost:
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    self.acting_player_actions -= card.cost
    placement = card.Change('position', position)
    return [engine.GlobalChange('acting_player_actions', self.acting_player_actions),
            placement]

  def PlantAtScene(self, card_id, position):
    card = self.GetCardById(card_id)
    if self.acting_player_actions < card.cost:
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    if self.GetLoomingComplicationAt(position):
      return [engine.PlayerWarning(
                  self.acting_player,
                  "There's alrady a looming complication there."
              )]
    self.acting_player_actions -= card.cost
    placement = card.Change('position', position)
    return [engine.GlobalChange('acting_player_actions', self.acting_player_actions),
            placement]

  def DropCard(self, held_id):
    held = self.GetCardById(held_id)
    drop = held.Change('holder', 0)
    return [drop]

  def AttachToCard(self, held_id, holder_id):
    held = self.GetCardById(held_id)
    holder = self.GetCardById(holder_id)
    attachment_trigger = engine.Trigger(
      object_class='card',
      object_id=held_id,
      matcher='ThisCardsHolderMoved',
      delete_matcher='ThisCardUnattached',
      function='MoveAttachedCard')
    self.reactive_triggers.append(attachment_trigger)
    attachment = held.Change('holder', holder_id)
    return [attachment]

  def AttachToSceneAtPosition(self, card_id, position):
    card = self.GetCardById(card_id)
    scene = self.GetSceneByPosition(position)
    attachment_trigger = engine.Trigger(
      object_class='card',
      object_id=card_id,
      matcher='ThisCardsSceneMoved',
      delete_matcher='ThisCardOutOfPlay',  #TODO: A trigger to allow unattachment
      function='MoveAttachedCard')
    self.reactive_triggers.append(attachment_trigger)
    placement = card.Change('position', position)
    reveal = card.Change('is_faceup', True)
    return [placement, reveal]

  def AttachToScene(self, card_id, scene_id):
    card = self.GetCardById(card_id)
    scene = self.GetSceneById(scene_id)
    attachment_trigger = engine.Trigger(
      object_class='card',
      object_id=card_id,
      matcher='ThisCardsSceneMoved',
      delete_matcher='ThisCardOutOfPlay',
      function='MoveAttachedCard')
    self.reactive_triggers.append(attachment_trigger)
    placement = card.Change('position', scene.position)
    reveal = card.Change('is_faceup', True)
    return [placement, reveal]

  def AttachTokenToScene(self, scene_id, token):
    scene = self.GetSceneById(scene_id)
    return [scene.Change('attached_token', token)]

  def AddSnagToScene(self, scene_id):
    scene = self.GetSceneById(scene_id)
    return [scene.Change('tokens', scene.tokens + ['S'])]

  def AvertEffect(self):
    if 'avertable' not in self.stack[-1].tags:
      return [engine.GameWarning('cannot avert this effect')]
    self.stack.pop()

  def DontAvertEffect(self):
    if 'avertable' not in self.stack[-1].tags:
      return [engine.GameWarning('cannot not avert this effect')]
    self.stack[-1].tags.remove('__awaiting_input')

  def PayAversionCost(self, *card_ids):
    cost = None
    position = None
    for tag in self.stack[-1].tags:
      if tag.startswith('aversioncost:'):
        cost = tag.split(':')[1]
    if not cost:
      return [engine.GameWarning('Something went wrong: no aversion cost found')]

    position = self.stack[-1].args[0]
    if not position:
      return [engine.GameWarning('Something went wrong: no position found')]

    changes = []
    for i, skill in enumerate(cost):
      card = self.GetCardById(card_ids[i])
      if card.position != position:
        # TODO, maybe: factor this out to allow for cards that use skill remotely
        return [engine.GameWarning("card %s isn't in position" % card_ids[i])]
      if skill == 'G':
        if card.skill_points[0] > 0:
          change = card.Change(
              'skill_points',
              [card.skill_points[0] - 1, card.skill_points[1]]
          )
        else:
          return [engine.GameWarning("card %s doesn't have the skillz" % card_ids[i])]
      elif skill =='L':
        if card.skill_points[1] > 0:
          change = card.Change(
              'skill_points',
              [card.skill_points[0], card.skill_points[1] - 1]
          )
        else:
          return [engine.GameWarning("card %s doesn't have the skillz" % card_ids[i])]
      changes.append(change)
    self.Push('AvertEffect')
    return changes

  ##############################################################################
  # Avertable and Positional Effects
  #
  # The first argument should always be a position.
  # This is where the effect happens and where the Crew can spend skill to avert
  # the effect.
  ##############################################################################

  def GuardEffect(self, position):
    scene = self.GetSceneByPosition(position)
    self.Do([('AttachTokenToScene', [scene.scene_id, 'G']),
             ('AddSnagToScene', [scene.scene_id]),
             ('StopOperation',),
            ])

  def LockEffect(self, position):
    scene = self.GetSceneByPosition(position)
    self.Do([('AttachTokenToScene', [scene.scene_id, 'L']),
             ('AddSnagToScene', [scene.scene_id]),
             ('StopOperation',),
            ])

  def SnagEffect(self, position):
    looming = self.GetLoomingComplicationAt(position)
    if looming:
      self.Push('DiscoverCardAt', [looming.card_id, position])
      return [engine.MessageWithObject('A complication was discovered at the scene.', 'card', looming.db_id)]
    else:
      self.Push('DiscoverTopOfDeck', [position])

  def DiscoverTopOfDeck(self, position):
    if self.powers_deck:
      top_card = self.GetCardById(self.powers_deck[-1])
      self.Push('DiscoverCardAt', [top_card.card_id, position])
      return [engine.MessageWithObject("The top card of the Powers' deck was discovered.", 'card', top_card.db_id)]

  def DiscoverCardAt(self, card_id, position):
    # Noop to allow WhenDiscovered triggers
    # This could execute the WhenDiscovered effect directly, one supposes
    pass

  #######################
  # Triggered Abilities #
  #######################

  def MoveAttachedCard(self, card_id, _, new_position):
    if new_position not in self.ACTIVE_POSITIONS:
      self.Push('TrashCard', [card_id])
    else:
      self.Push('MoveCard', [card_id, new_position])
    return []

  #################
  # The Operation #
  #################

  def StartOperation(self, position):
    self.Do([('RevealActorsInPosition', [position]),
             ('StartOfOperation', [position]),
             ('SearchScene', [position]),
             ('EndOfOperation', [position]),
            ])
    scene = self.GetSceneByPosition(position)
    return [engine.MessageWithObject("The Crew has started an operation.", 'card', scene.db_id)]

  def RevealActorsInPosition(self, position):
    revelations = []
    for card in self.cards:
      if card.position == position and card.card_type == 'actor' and not card.is_faceup:
        # This is a shortcut that doesn't allow for any "when revealed" triggers.
        revelations.append(card.Change('is_faceup', True))
    return revelations

  def StartOfOperation(self, position):
    """Allow triggered effects and resolve the attached token, if any.

    Again, this is a bit of a hack for the attached token, but it should work.
    """
    scene = self.GetSceneByPosition(position)
    if scene.attached_token == 'G':
      self.Push('GuardEffect', [position], ['__awaiting_input',
                                            '__waiting_on:1',
                                            'avertable',
                                            'aversioncost:G'], 'token', 0)
    elif scene.attached_token == 'L':
      self.Push('LockEffect', [position], ['__awaiting_input',
                                           '__waiting_on:1',
                                           'avertable',
                                           'aversioncost:L'], 'token', 1)
    return [scene.Change('attached_token', '')]

  def SearchScene(self, position):
    """Check to make sure there's still an operative."""
    scene = self.GetSceneByPosition(position)
    for card in self.cards:
      if card.CanDiscoverCardsAt(position):
        self.Push('DiscoverTokenAtPosition', [position])
        return
    self.Push('StopOperation')

  def DiscoverTokenAtPosition(self, position):
    scene = self.GetSceneByPosition(position)
    tokens_here = scene.tokens[:]  # copy
    selected_token = random.choice(tokens_here)
    tokens_here.remove(selected_token)
    token_change = scene.Change('tokens', tokens_here)
    if selected_token == 'G':
      self.Push('GuardTokenDiscovered', [position])
    elif selected_token == 'L':
      self.Push('LockTokenDiscovered', [position])
    elif selected_token == 'S':
      self.Push('SnagTokenDiscovered', [position])
    elif selected_token in ('R2', 'R3', 'R4'):
      self.Push('ResolutionDiscovered', [selected_token])
    return [token_change]

  def GuardTokenDiscovered(self, position):
    self.Push('GuardEffect', [position], ['__awaiting_input', 'avertable', 'aversioncost:G'], 'token', 0)
    return [engine.GlobalMessage('The crew ran into a guard.')]

  def LockTokenDiscovered(self, position):
    self.Push('LockEffect', [position], ['__awaiting_input', 'avertable', 'aversioncost:L'], 'token', 1)
    return [engine.GlobalMessage('The crew found a lock.')]

  def SnagTokenDiscovered(self, position):
    self.Push('SnagEffect', [position])
    return [engine.GlobalMessage("There's been a snag in the operation.")]

  def ResolutionDiscovered(self, resolution):
    points = int(resolution[1])
    self.Do([('Score', [self.CREW, points]),
             ('RaiseThreat1',)])
    return [engine.GlobalMessage('Sick rips! The crew stole %s points.' % points)]

  def StopOperation(self):
    """Fast forwards to the EndOfOperation."""
    while self.stack[-1].function != 'EndOfOperation':
      self.stack.pop()

  def EndOfOperation(self, position):
    """Noop event to allow triggered effects."""
    pass
