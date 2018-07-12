#!/usr/bin/python

import engine
import random

"""
cost: (int) Action cost to play the card
card_type: (str)
card_subtypes: (list of str)
unique: (bool)
play_function: (str) The name of a function to run when the card is played.
target_type: (str) A type identifier for additional arguments to play_function
            NOTE: maybe this should be (list of str)
effects: list of tuples: ((str) trigger matcher, (str) stack function, (str or None) aversion cost)
         Note that the matcher for avertable effects will need to return a position.
"""

CARDS = {
    # The Don
    1000: {'cost': 0,
           'card_type': 'actor',
           'card_subtypes': ['boss'],
           'unique': True,
           'play_function': 'PlaceInOffice',
           'abilities': ['Move1InfluenceHere'],
          },
    # Bouncer
    1001: {'cost': 2,
           'card_type': 'actor',
           'unique': False,
           'play_function': 'PlaceInSceneFacedown',
           'target_type': 'scene_position',
           'effects': [('StartOfOperationHere', 'BounceAnOperativeHere', 'G')],
          },
    # Confiscation
    1002: {'cost': 1,
           'card_type': 'event',
           'play_function': 'Confiscation',
          },
    # Cop on the Take
    1003: {'cost': 1,
           'card_type': 'complication',
           'play_function': 'PlantAtScene',
           'target_type': 'scene_position',
           'effects': [('WhenDiscovered', 'AttachToSceneAtPosition', None),
                       ('StartOfOperationHere', 'StopOperation', 'G'),
                       ('EndOfOperationHere', 'MoveOperativesHome', None)],
          },
    # Doorman
    1004: {'cost': 2,
           'card_type': 'actor',
           'unique': False,
           'play_function': 'PlaceInSceneFacedown',
           'target_type': 'scene_position',
           'effects': [('StartOfOperationHere', 'TrashRandomItemHere', 'G')],
          },
    # Durante da Firenze
    1005: {'cost': 1,
           'card_type': 'actor',
           'unique': True,
           'play_function': 'PlaceInOffice',
           'effects': [('StartOfOperationAnywhere', 'TurnDuranteOffThere', None),
                       ('OnStartOfPowersTurn', 'Durante', None)],
           # Maybe move this so the trigger is created when played?
           # Probably, most other triggers should be created similarly
           # at the cost of complicating the play_function somewhat.
           #
           # Alternately, the default Play functions could be the thing that
           # actually creates the effects triggers. Then a when_discovered attribute
           # would need to be a thing for complications that are in the deck.
          },
    # Get Outta Here
    1006: {'cost': 3,
           'card_type': 'event',
           'play_function': 'GetOuttaHere',
           'target_type': 'scene',
          },
    # Jimmy
    1007: {'cost': 2,
           'card_type': 'actor',
           'unique': True,
           'play_function': 'PlaceInSceneFacedown',
           'target_type': 'scene_position',
           'effects': [('StartOfOperationHere', 'RaiseThreat1', 'G')],
          },
    # Little Birdie
    1008: {'cost': 1,
           'card_type': 'complication',
           'play_function': 'PlantAtScene',
           'target_type': 'scene_position',
           'effects': [('WhenDiscovered', 'LittleBirdie', None)],
          },
    # Locked Door
    1009: {'cost': 2,
           'card_type': 'complication',
           'play_function': 'PlantAtScene',
           'target_type': 'scene_position',
           'effects': [('WhenDiscovered', 'AttachToSceneAtPosition', None),
                       ('StartOfOperationHere', 'StopOperation', 'L')],
          },
    # Protection
    1010: {'cost': 2,
           'card_type': 'complication',
           'play_function': 'PlantAtScene',
           'target_type': 'scene_position',
           'effects': [('WhenDiscovered', 'Protection', None)],
          },
    # Retribution
    1011: {'cost': 3,
           'card_type': 'event',
           'play_function': 'Retribution',
          },
    # Take the Cannoli
    # Note: This card calls for input from the Crew on the Powers turn.
    1012: {'cost': 3,
           'card_type': 'event',
           'play_function': 'TakeTheCannoli',
           'target_type': 'scene_position',
           'target_reqs': [engine.TargetReq(attr='subtypes', e_value='private')],
          },
    # Welcoming Committee
    1013: {'cost': 1,
           'card_type': 'complication',
           'play_function': 'PlantAtScene',
           'target_type': 'scene_position',
           'effects': [('WhenDiscovered', 'WelcomingCommittee', None)],
          },
    # You Broke My Heart
    1014: {'cost': 2,
           'card_type': 'event',
           'play_function': 'YouBrokeMyHeart',
           'effects': [('WhenCrewScores', 'YBMHCanBePlayed', None)],
          },
    # You Were Warned
    1015: {'cost': 1,
           'card_type': 'event',
           'play_function': 'YouWereWarned',
          },

    ############################################################
    # These aren't the Mob, but I'm putting them here for now. #
    ############################################################

    # Fast Forward
    1101: {'cost': 3,
           'card_type': 'event',
           'play_function': 'FastForward',
          },
}


class MobCards(object):
  """Mixin for Mob card functions"""

  def Confiscation(self, card_id):
    card = self.GetCardById(card_id)
    if self.acting_player_actions < card.cost:
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    if self.threat_level < 2:
      return [engine.PlayerWarning(self.acting_player, "The Threat Level isn't 2 or higher.")]
    valid_targets = []
    for target in self.cards:
      if (target.position in self.ACTIVE_POSITIONS
          and target.card_type == 'item'):
        valid_targets.append(target.card_id)
    if not valid_targets:
      return [engine.PlayerWarning(self.acting_player, "There are no items to trash.")]
    self.acting_player_actions -= card.cost
    placement = card.Change('position', 'discard_2')
    reveal = card.Change('is_faceup', True)
    message = engine.MessageWithObject('The Mob is confiscating an item.', 'card', card.db_id)
    changes = [engine.GlobalChange('acting_player_actions', self.acting_player_actions),
               placement,
               reveal,
               message]
    self.Push('TrashCard',
               valid_targets,
               ['__awaiting_input', '__waiting_on:2'])
    return changes

  def BounceAnOperativeHere(self, position):
    valid_targets = []
    for card in self.cards:
      if card.position == position and card.card_type == 'operative':
        valid_targets.append(card.card_id)
    stack_id = random.randint(1, 1<<32)
    self.Do([('RequestSelection',
              valid_targets,
              ['__awaiting_input', '__waiting_on:1', 'index:0', 'type:card', 'stack_id:%s' % stack_id]),
             ('MoveCard', ['', 'crew_hand'], [], 'StackItem', stack_id)])

  def BounceCrewCard(self, card_id):
    self.Push('MoveCard', [card_id, 'hideout'])

  def TrashRandomItemHere(self, position):
    valid_targets = []
    for target in self.cards:
      if target.position == position and target.card_type == 'item':
         valid_targets.append(target.card_id)
    if valid_targets:
      target_id = random.choice(valid_targets)
      self.Push('TrashCard', [target_id])

  def TurnDuranteOffThere(self, position):
    for card in self.cards:
      if card.db_id == 1005:  # this is hacky and bad
        card.statuses.append('off_at:%s' % position)

  def Durante(self, card_id):
    card = self.GetCardById(card_id)
    off_status = 'off_at:%s' % card.position
    if card.position.startswith('scene_') and off_status not in card.statuses:
      self.Push('AddInfluenceToOffice', [2])
    # Turn Durante back on for subsequent turns
    card.statuses = []

  def GetOuttaHere(self, card_id, scene_id):
    card = self.GetCardById(card_id)
    if self.acting_player_actions < card.cost:
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    scene = self.GetSceneById(scene_id)
    self.acting_player_actions -= card.cost
    message = engine.MessageWithObject('Get outta here, ya mooks!', 'card', card.db_id)
    changes = [engine.GlobalChange('acting_player_actions', self.acting_player_actions),
               message]

    self.Do([('AttachToScene', [card_id, scene_id]),
             ('MoveOperativesHome', [scene.position])])
    if 'private' not in scene.subtypes:
      changes.append(scene.Change('subtypes', scene.subtypes + ['private']))
    return changes

  def LittleBirdie(self, card_id, unused_position):
    self.Do([('RaiseThreat1',),
             ('TrashCard', [card_id])])

  def Protection(self, card_id, position):
    self.Do([('TrashRandomOperativeHere',
              [position],
              ['__awaiting_input', '__waiting_on:1', 'avertable', 'aversioncost:GG'],
              'card',
              card_id),
             ('TrashCard', [card_id])])

  def TrashRandomOperativeHere(self, position):
    valid_targets = []
    for target in self.cards:
      if target.position == position and target.card_type == 'operative':
         valid_targets.append(target.card_id)
    if valid_targets:
      target_id = random.choice(valid_targets)
      self.Push('TrashCard', [target_id])

  def Retribution(self, card_id):
    # This could also potentially be done with a target.
    card = self.GetCardById(card_id)
    if self.acting_player_actions < card.cost:
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    if self.threat_level < 4:
      return [engine.PlayerWarning(self.acting_player, "The Threat Level isn't 4 or higher.")]
    valid_targets = []
    for target in self.cards:
      if (target.position in self.ACTIVE_POSITIONS
          and target.card_type == 'operative'):
        valid_targets.append(target.card_id)
    if not valid_targets:
      return [engine.PlayerWarning(self.acting_player, "There are no operatives to trash.")]
    self.acting_player_actions -= card.cost
    placement = card.Change('position', 'discard_2')
    reveal = card.Change('is_faceup', True)
    message = engine.MessageWithObject('The Mob is getting its revenge.', 'card', card.db_id)
    changes = [engine.GlobalChange('acting_player_actions', self.acting_player_actions),
               placement,
               reveal,
               message]
    self.Push('TrashCard',
               valid_targets,
               ['__awaiting_input', '__waiting_on:2'])
    return changes

  def TakeTheCannoli(self, card_id, position):
    card = self.GetCardById(card_id)
    if self.acting_player_actions < card.cost:
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    scene = self.GetSceneByPosition(position)
    if 'private' not in scene.subtypes:
      return [engine.PlayerWarning(self.acting_player, "That scene isn't private.")]
    valid_targets = []
    for target in self.cards:
      if target.position == position and target.card_type == 'operative':
        valid_targets.append(target.card_id)
    if not valid_targets:
      return [engine.PlayerWarning(self.acting_player, "There are no operatives to trash there.")]

    self.acting_player_actions -= card.cost
    placement = card.Change('position', 'discard_2')
    reveal = card.Change('is_faceup', True)
    message = engine.MessageWithObject('Leave the gun.', 'card', card.db_id)
    changes = [engine.GlobalChange('acting_player_actions', self.acting_player_actions),
               placement,
               reveal,
               message]

    self.Push('TrashAnOperativeHere',
              [position],
              ['__awaiting_input', '__waiting_on:1', 'avertable', 'aversioncost:G'],
              'card',
              card_id)
    return changes

  def TrashAnOperativeHere(self, position):
    valid_targets = []
    for target in self.cards:
      if target.position == position and target.card_type == 'operative':
        valid_targets.append(target.card_id)
    if valid_targets:
      self.Push('TrashCard', valid_targets, ['__awaiting_input', '__waiting_on:2', 'type:card'])

  def WelcomingCommittee(self, card_id, position):
    self.Do([('Welcome',
              [position],
              ['__awaiting_input', '__waiting_on:1', 'avertable', 'aversioncost:G'],
              'card',
              card_id),
             ('TrashCard', [card_id])])

  def Welcome(self, position):
    here = self.GetSceneByPosition(position)
    if 'private' in here.subtypes:
      # This wasn't meant to be random, but it would allow the turn separation to be maintained.
      # self.Push('TrashRandomOperativeHere', [position])
      self.Push('TrashAnOperativeHere', [position])
    self.Push('RaiseThreat1')

  def YouBrokeMyHeart(self, card_id):
    card = self.GetCardById(card_id)
    if self.acting_player_actions < card.cost:
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    if 'allowed' not in card.statuses:
      return [engine.PlayerWarning(self.acting_player, "The Crew didn't score last turn.")]
    self.acting_player_actions -= card.cost
    placement = card.Change('position', 'discard_2')
    reveal = card.Change('is_faceup', True)
    message = engine.MessageWithObject('"You broke my heart"', 'card', card.db_id)
    changes = [engine.GlobalChange('acting_player_actions', self.acting_player_actions),
               placement,
               reveal,
               message]
    self.Push('RaiseThreat1')
    return changes

  def YBMHCanBePlayed(self, card_id):
    this = self.GetCardById(card_id)
    if 'allowed' not in this.statuses:
      this.statuses.append('allowed')
    end_of_turn_trigger = engine.Trigger(
        object_class='card',
        object_id=card_id,
        matcher='OnEndOfPowersTurn',
        delete_matcher='OnEndOfPowersTurn',
        function='YBMHCannotBePlayed')
    self.reactive_triggers.append(end_of_turn_trigger)

  def YBMHCannotBePlayed(self, card_id):
    this = self.GetCardById(card_id)
    if 'allowed' in this.statuses:
      this.statuses.remove('allowed')

  def YouWereWarned(self, card_id):
    card = self.GetCardById(card_id)
    if self.acting_player_actions < card.cost:
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    self.acting_player_actions -= card.cost
    placement = card.Change('position', 'discard_2')
    reveal = card.Change('is_faceup', True)
    message = engine.MessageWithObject('The Mob has issued a warning.', 'card', card.db_id)
    changes = [engine.GlobalChange('acting_player_actions', self.acting_player_actions),
               placement,
               reveal,
               message]
    # TODO: Yes, this is incorrect in that it triggers for every operation.
    #       I'm ignoring that and moving on for now.
    warning_trigger = engine.Trigger(
        object_class='card',
        object_id=card_id,
        matcher='StartOfOperationAnywhere',
        delete_matcher='OnEndOfCrewTurn',
        function='RaiseThreat1')
    self.reactive_triggers.append(warning_trigger)
    return changes

  def FastForward(self, card_id):
    card = self.GetCardById(card_id)
    if self.acting_player_actions < card.cost:
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    self.acting_player_actions -= card.cost
    placement = card.Change('position', 'discard_2')
    reveal = card.Change('is_faceup', True)
    message = engine.MessageWithObject('Fast Forward', 'card', card.db_id)
    changes = [engine.GlobalChange('acting_player_actions', self.acting_player_actions),
               placement,
               reveal,
               message]
    self.Push('AddInfluenceToOffice', [7])
    return changes

  # TODO: make the events a little cleaner with either a helper function or an
  #       @event decorator to handle checking costs, discarding the card
  #       and sending the client message
