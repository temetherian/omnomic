#!/usr/bin/python

import engine
import random

CARDS = {
    # 1, 2, 3, Go!
    1: {'cost': 1,
        'card_type': 'event',
        'play_function': 'OneTwoThreeGo',
        'target_type': 'scene_position',
       },
    # A Surprising Twist
    2: {'cost': 2,
        'card_type': 'event',
        'play_function': 'SurprisingTwist',
       },
    # Double Lift
    3: {'cost': 1,
        'card_type': 'event',
        'play_function': 'DoubleLift',
        'target_type': 'scene_position',
       },
    # Garland McKinnon
    4: {'cost': 3,
        'card_type': 'operative',
        'unique': True,
        'play_function': 'PlaceInHideout',
        'skill_cap': [2, 0],
        'abilities': ['GarlandAbility'],
       },
    # Power Nap
    5: {'cost': 1,
        'card_type': 'event',
        'play_function': 'PowerNap',
        'target_type': 'card',
        'target_reqs': [engine.TargetReq(attr='card_type', e_value='operative')],
       },
    # Pretty Face
    6: {'cost': 2,
        'card_type': 'operative',
        'play_function': 'PlaceInHideout',
        'abilities': ['PrettyFaceAbility'],
       },
    # Rebel Henley
    7: {'cost': 4,
        'card_type': 'operative',
        'unique': True,
        'play_function': 'PlaceInHideout',
        'skill_cap': [0, 2],
        'abilities': ['RebelAbility'],
       },
    # Reconnaissance
    8: {'cost': 1,
        'card_type': 'event',
        'play_function': 'Reconnaissance',
       },
    # So. Here's the Plan...
    9: {'cost': 2,
        'card_type': 'event',
        'play_function': 'SoHeresThePlan',
       },
    # The Cheat
    10: {'cost': 3,
         'card_type': 'operative',
         'unique': True,
         'play_function': 'PlaceInHideout',
         'skill_cap': [0, 2],
         'abilities': ['CheatAbility'],
        },
    # The Sneak
    11: {'cost': 3,
         'card_type': 'operative',
         'unique': True,
         'play_function': 'PlaceInHideout',
         'skill_cap': [1, 0],
         'abilities': ['SneakAbility'],
        },
    # Thieves' Tools
    12: {'cost': 3,
         'card_type': 'item',
         'play_function': 'PlaceInHideout',
         'skill_cap': [0, 1],
        },
    # Tranquilizer Gun
    13: {'cost': 2,
         'card_type': 'item',
         'play_function': 'PlaceInHideout',
         'skill_cap': [1, 0],
        },
    # Whisper Earrings
    14: {'cost': 2,
         'card_type': 'item',
         'play_function': 'PlaceInHideout',
         'abilities': ['Whisper'],
        },
    # Yerba Mate
    15: {'cost': 3,
         'card_type': 'item',
         'play_function': 'InitializeYerbaMate',
        },

    ############################################################
    # Neutral cards that are here for the demo.                #
    ############################################################

    # False Alarm
    102: {'cost': 2,
          'card_type': 'event',
          'play_function': 'FalseAlarm',
         },
}


class ProsCards(object):
  """Mixin for Pros card functions"""

  def OneTwoThreeGo(self, card_id, position):
    card = self.GetCardById(card_id)
    if self.acting_player_actions < card.cost:
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    self.acting_player_actions -= card.cost
    placement = card.Change('position', 'discard_1')
    reveal = card.Change('is_faceup', True)
    message = engine.MessageWithObject("One. Two. Three.", 'card', card.db_id)
    changes = [engine.GlobalChange('acting_player_actions', self.acting_player_actions),
               placement,
               reveal,
               message]
    self.Do([('OneTwoThreeGoPicker', [position]),
             ('OneTwoThreeGoPicker', [position]),
             ('OneTwoThreeGoPicker', [position]),])
    return changes

  def OneTwoThreeGoPicker(self, position):
    valid_targets = ['__cancel']
    for card in self.cards:
      if (card.position in self.ACTIVE_POSITIONS
          and card.position != position
          and card.player == self.CREW):
        valid_targets.append(card.card_id)
    stack_id = random.randint(1, 1<<32)
    self.Do([('RequestSelection',
              valid_targets,
              ['__awaiting_input', '__waiting_on:1', 'index:0', 'type:card', 'stack_id:%s' % stack_id]),
             ('MoveCard', ['', position], [], 'StackItem', stack_id)])

  def SurprisingTwist(self, card_id):
    card = self.GetCardById(card_id)
    if self.acting_player_actions < card.cost:
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    self.acting_player_actions -= card.cost
    placement = card.Change('position', 'discard_1')
    reveal = card.Change('is_faceup', True)
    message = engine.MessageWithObject("Look over here!", 'card', card.db_id)
    changes = [engine.GlobalChange('acting_player_actions', self.acting_player_actions),
               placement,
               reveal,
               message]

    todo = []
    remove_targets = []
    add_targets = []
    for scene in self.scenes:
      if scene.position in self.ACTIVE_POSITIONS:
        if scene.influence > 0:
          remove_targets.append(scene.scene_id)
        if scene.GetResolutionInfo()[0]:
          add_targets.append(scene.scene_id)
    if remove_targets:
      stack_id = random.randint(1, 1<<32)
      todo.extend(
          [('RequestSelection',
            remove_targets,
            ['__awaiting_input', '__waiting_on:1', 'index:0', 'type:scene', 'stack_id:%s' % stack_id]),
           ('AddInfluenceToScene', ['', -1], [], 'StackItem', stack_id)]
      )
    if add_targets:
      stack_id = random.randint(1, 1<<32)
      todo.extend(
          [('RequestSelection',
            add_targets,
            ['__awaiting_input', '__waiting_on:1', 'index:0', 'type:scene', 'stack_id:%s' % stack_id]),
           ('AddInfluenceToScene', ['', 2], [], 'StackItem', stack_id)]
      )
    self.Do(todo)
    return changes

  def DoubleLift(self, card_id, position):
    card = self.GetCardById(card_id)
    if self.acting_player_actions < card.cost:
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    if not position.startswith('scene'):
      return [engine.GameWarning('illegal play')]
    for op in self.cards:
      if op.CanDiscoverCardsAt(position):
        break
    else:
      return [engine.PlayerWarning(self.acting_player, "There's nobody there who can perform the Double Lift.")]

    self.acting_player_actions -= card.cost
    placement = card.Change('position', 'discard_1')
    reveal = card.Change('is_faceup', True)
    message = engine.MessageWithObject('"Is this your card?"', 'card', card.db_id)
    changes = [engine.GlobalChange('acting_player_actions', self.acting_player_actions),
               placement,
               reveal,
               message]

    extra_token_trigger = engine.Trigger(
        object_class='card',
        object_id=card_id,
        matcher='OnSearchScene',
        delete_matcher='OnSearchScene',  # Only add the extra Search once.
        function='SearchScene')
    self.proactive_triggers.append(extra_token_trigger)

    add_snag_trigger = engine.Trigger(
        object_class='card',
        object_id=card_id,
        matcher='EndOfOperationAtScene',
        delete_matcher='EndOfOperationAtScene',
        function='AddSnagToScene')
    self.reactive_triggers.append(add_snag_trigger)

    self.Push('StartOperation', [position])
    return changes

  def OnSearchScene(self, object_class, object_id, stack_item, changes):
    if stack_item.function == 'SearchScene':
      here = stack_item.args[0]
      return True, [here]
    return False, None

  def DoubleLiftDeleter(self, *args):
    is_search_scene = self.OnSearchScene(*args)
    if is_search_scene[0]:
      return is_search_scene
    return self.OnEndOfOperation(*args)

  def GarlandAbility(self, card_id):
    if self.acting_player_actions < 1:
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    card = self.GetCardById(card_id)
    if not card.position.startswith('scene_'):
      return [engine.PlayerWarning(self.acting_player, "Garland is not at a scene.")]
    scene = self.GetSceneByPosition(card.position)
    if card.skill_points[0] < scene.influence:
      self.acting_player_actions -= 1
      new_skill = [scene.influence, card.skill_points[1]]
      change = card.Change('skill_points', new_skill)
      return [engine.GlobalChange('acting_player_actions',
                                  self.acting_player_actions),
              change]
    else:
      return []

  def PowerNap(self, card_id, napper):
    card = self.GetCardById(card_id)
    if self.acting_player_actions < card.cost:
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    napper = self.GetCardById(napper)
    if napper.position not in self.ACTIVE_POSITIONS:
      return [engine.PlayerWarning(self.acting_player, "That operative is not in play.")]

    self.acting_player_actions -= card.cost
    placement = card.Change('position', 'discard_1')
    reveal = card.Change('is_faceup', True)
    message = engine.MessageWithObject("Power Nap", 'card', card.db_id)
    changes = [engine.GlobalChange('acting_player_actions', self.acting_player_actions),
               placement,
               reveal,
               message]
    if napper.skill_cap:
      changes.append(
          napper.Change('skill_points',
                        [max(napper.skill_points[0], napper.skill_cap[0]),
                         max(napper.skill_points[1], napper.skill_cap[1])]
                       )
      )
    return changes

  def PrettyFaceAbility(self, card_id):
    if self.acting_player_actions < 1:
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    card = self.GetCardById(card_id)
    if not card.position.startswith('scene_'):
      return [engine.PlayerWarning(self.acting_player, "Pretty Face is not at a scene.")]
    valid_targets = []
    other_scenes = []
    for scene in self.scenes:
      if scene.position != card.position and scene.position in self.ACTIVE_POSITIONS:
        other_scenes.append(scene.position)
    if not other_scenes:
      return [engine.PlayerWarning(self.acting_player, "There are no other scenes to move to.")]

    for actor in self.cards:
      if actor.card_type == 'actor' and actor.position == card.position:
        valid_targets.append(actor.card_id)
    if not valid_targets:
      return [engine.PlayerWarning(self.acting_player, "There are no actors here.")]

    self.acting_player_actions -= 1
    stack_id = random.randint(1, 1<<32)
    self.Do([('RequestSelection', valid_targets,
                 ['__awaiting_input', '__waiting_on:1', 'index:0', 'type:card', 'stack_id:%s' % stack_id]),
             ('RequestSelection', other_scenes,
                 ['__awaiting_input', '__waiting_on:1', 'index:1', 'type:scene_position', 'stack_id:%s' % stack_id]),
             ('MoveCard', [card_id, ''], [], 'StackItem', stack_id),
             ('MoveCard', ['', ''], [], 'StackItem', stack_id),
            ])
    return [engine.GlobalChange('acting_player_actions',
                                self.acting_player_actions)]

  def RebelAbility(self, card_id):
    if self.acting_player_actions < 1:
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    card = self.GetCardById(card_id)
    if card.position not in self.ACTIVE_POSITIONS:
      return [engine.PlayerWarning(self.acting_player, "Rebel is not in play.")]
    if card.skill_points[1] < card.skill_cap[1]:
      self.acting_player_actions -= 1
      new_skill = [card.skill_points[0], card.skill_points[1] + 1]
      change = card.Change('skill_points', new_skill)
      return [engine.GlobalChange('acting_player_actions',
                                  self.acting_player_actions),
              change]
    else:
      return []

  def Reconnaissance(self, card_id):
    # This probably isn't terribly hard, but I just don't feel like implementing it right now.
    pass

  def SoHeresThePlan(self, card_id):
    card = self.GetCardById(card_id)
    if self.acting_player_actions < card.cost:
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    self.acting_player_actions -= card.cost
    placement = card.Change('position', 'discard_1')
    reveal = card.Change('is_faceup', True)
    message = engine.MessageWithObject("So, here's the plan...", 'card', card.db_id)
    changes = [engine.GlobalChange('acting_player_actions', self.acting_player_actions),
               placement,
               reveal,
               message]
    for op in self.cards:
      if op.card_type == 'operative' and op.skill_cap and op.position == 'hideout':
        if op.skill_points[0] < op.skill_cap[0]:
          changes.append(op.Change('skill_points', [op.skill_points[0] + 1, op.skill_points[1]]))
        elif op.skill_points[1] < op.skill_cap[1]:
          changes.append(op.Change('skill_points', [op.skill_points[0], op.skill_points[1] + 1]))
    return changes

  def CheatAbility(self, card_id):
    # We're discarding instead of attaching because the game can keep track of
    # enhancement, so we don't need a physical reminder.
    if self.acting_player_actions < 1:
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    card = self.GetCardById(card_id)
    if card.position not in self.ACTIVE_POSITIONS:
      return [engine.PlayerWarning(self.acting_player, "The Cheat is not in play.")]
    copy_in_hand = None
    for other in self.cards:
      if other.db_id == card.db_id and other.position == 'crew_hand':
        copy_in_hand = other
    if not copy_in_hand:
      return [engine.PlayerWarning(self.acting_player, "You don't have another copy of The Cheat in hand.")]
    self.acting_player_actions -= 1
    return [engine.GlobalChange('acting_player_actions', self.acting_player_actions),
            copy_in_hand.Change('position', 'discard_%s' % self.acting_player),
            card.Change('skill_cap', [0, 3]),
            card.Change('abilities', []),
            card.Change('card_subtypes', ['enhanced']),
            card.Change('db_id', 10010)]

  def SneakAbility(self, card_id):
    # We're discarding instead of attaching because the game can keep track of
    # enhancement, so we don't need a physical reminder.
    if self.acting_player_actions < 1:
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    card = self.GetCardById(card_id)
    if card.position not in self.ACTIVE_POSITIONS:
      return [engine.PlayerWarning(self.acting_player, "The Sneak is not in play.")]
    copy_in_hand = None
    for other in self.cards:
      if other.db_id == card.db_id and other.position == 'crew_hand':
        copy_in_hand = other
    if not copy_in_hand:
      return [engine.PlayerWarning(self.acting_player, "You don't have another copy of The Sneak in hand.")]
    self.acting_player_actions -= 1
    return [engine.GlobalChange('acting_player_actions', self.acting_player_actions),
            copy_in_hand.Change('position', 'discard_%s' % self.acting_player),
            card.Change('skill_cap', [3, 0]),
            card.Change('abilities', []),
            card.Change('card_subtypes', ['enhanced']),
            card.Change('db_id', 10011)]

  def InitializeWhisperEarrings(self, card_id):
    #TODO: Whisper Earrings' unequipment restriction
    pass

  def Whisper(self, card_id):
    if self.acting_player_actions < 1:
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    card = self.GetCardById(card_id)
    if card.holder:
      holder = self.GetCardById(card.holder)
      if holder.skill_cap:
        if holder.skill_points[0] < holder.skill_cap[0]:
          self.acting_player_actions -= 1
          return [engine.GlobalChange('acting_player_actions', self.acting_player_actions),
                  holder.Change('skill_points', [holder.skill_points[0] + 1, holder.skill_points[1]])]
        elif holder.skill_points[1] < holder.skill_cap[1]:
          self.acting_player_actions -= 1
          return [engine.GlobalChange('acting_player_actions', self.acting_player_actions),
                  holder.Change('skill_points', [holder.skill_points[0], holder.skill_points[1] + 1])]
    return []

  def InitializeYerbaMate(self, card_id):
    card = self.GetCardById(card_id)
    if self.acting_player_actions < card.cost:
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    self.acting_player_actions -= card.cost
    placement = card.Change('position', 'hideout')
    reveal = card.Change('is_faceup', True)
    counters = card.Change('counters', 6)
    start_of_turn_trigger = engine.Trigger(
      object_class='Card',
      object_id=card_id,
      matcher='OnStartOfCrewTurn',
      delete_matcher='ThisCardOutOfPlay',
      function='YerbaSkill')
    self.reactive_triggers.append(start_of_turn_trigger)
    changes = [engine.GlobalChange('acting_player_actions', self.acting_player_actions),
               placement,
               reveal,
               counters]
    return changes

  def YerbaSkill(self, card_id):
    card = self.GetCardById(card_id)
    changes = [card.Change('counters', card.counters - 1)]
    if card.holder:
      holder = self.GetCardById(card.holder)
      # There should be a helper for this.
      if holder.skill_cap:
        if holder.skill_points[0] < holder.skill_cap[0]:
          # We're cheating and taking advantage of the fact that the demo
          # operatives only have one skill type.
          changes.append(holder.Change('skill_points', [holder.skill_points[0] + 1, holder.skill_points[1]]))
        elif holder.skill_points[1] < holder.skill_cap[1]:
          changes.append(holder.Change('skill_points', [holder.skill_points[0], holder.skill_points[1] + 1]))
    if card.counters == 0:
      self.Push('TrashCard', card_id)
    return changes

  def FalseAlarm(self, card_id):
    card = self.GetCardById(card_id)
    if self.acting_player_actions < card.cost:
      return [engine.PlayerWarning(self.acting_player, "You don't have enough actions.")]
    self.acting_player_actions -= card.cost
    placement = card.Change('position', 'discard_1')
    reveal = card.Change('is_faceup', True)
    message = engine.MessageWithObject("Never mind, false alarm.", 'card', card.db_id)
    changes = [engine.GlobalChange('acting_player_actions', self.acting_player_actions),
               placement,
               reveal,
               message]
    self.Push('LowerThreat1')
    return changes
