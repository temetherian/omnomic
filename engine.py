#!/usr/bin/python

import datetime
import logging

from google.appengine.ext import ndb

###################
# Change Messages #
###################


class GlobalChange(object):
  def __init__(self, change_type, msg):
    """
    Args:
      change_type: (str)
      messages: (str)
    """
    self.change_type = change_type
    self.message = msg

  def ChangeForPlayer(self, _):
    return self.message


class GameChange(object):
  def __init__(self, change_type, messages):
    """
    Args:
      change_type: (str)
      messages: dict of player_id (int) -> (str)
    """
    self.change_type = change_type
    self.messages = messages

  def ChangeForPlayer(self, player_id):
    return self.messages[player_id]


class GameObjectChange(object):
  def __init__(self, object_type, object_id, attr, prev, new, messages):
    """
    Args:
      object_type: (str)
      object_id: (int)
      attr: (str)
      prev: previous value of the attr
      new: new value of the attr
      messages: dict of player_id (int) -> (str)
    """
    self.change_type = object_type
    self.object_id = object_id
    self.prev = prev
    self.new = new
    self.messages = messages

  def ChangeForPlayer(self, player_id):
    return self.messages[player_id]


class GameWarning(object):
  def __init__(self, msg):
    self.message = msg
    self.change_type = 'errors'

  def ChangeForPlayer(self, _):
    return self.message


class PlayerWarning(object):
  def __init__(self, player_id, msg):
    self.player_id = player_id
    self.message = msg
    self.change_type = 'errors'

  def ChangeForPlayer(self, player_id):
    if player_id == self.player_id:
      return self.message


class GlobalMessage(object):
  def __init__(self, msg):
    self.message = msg
    self.change_type = 'message'

  def ChangeForPlayer(self, _):
    return self.message


class MessageWithObject(object):
  def __init__(self, msg, object_class, db_id):
    self.message = msg
    self.change_type = 'message_with_object'
    self.object_class = object_class
    self.db_id = db_id

  def ChangeForPlayer(self, _):
    return {'message': self.message,
            'object_class': self.object_class,
            'db_id': self.db_id}


###############################################################################
# Game State Storage                                                          #
#                                                                             #
# It would be nice to abstract this from the specifics of the implementation. #
###############################################################################


class TargetReq(ndb.Model):
  attr = ndb.StringProperty()
  # operator
  e_value = ndb.GenericProperty()


class StackItem(ndb.Model):
  """An item on the game's stack.

  function: the name of a method for the game
  args: the arguments to pass to that method
  tags: tags to describe the method
  owner_class: class of the object that put this on the stack
  owner_id: id of the object that put this on the stack

  The owner attributes are optional, as they have no game function.
  If present, the client will be informed of the owner object.
  """
  function = ndb.StringProperty()
  args = ndb.GenericProperty(repeated=True)
  tags = ndb.StringProperty(repeated=True)
  owner_class = ndb.StringProperty()
  owner_id = ndb.IntegerProperty()


class Trigger(ndb.Model):
  """A reaction to something hitting or coming off the top of the stack.

  Proactive triggers are currently implemented by placing them on the stack as
  soon as their trigger is added to the stack. They're given the triggering
  StackItem as an argument, and should account for that StackItem disappearing
  from the stack (being prevented).

  Matchers could theortically Push directly to the stack, but doing so could
  cause problems with simultaneous triggers.

  object_class: The class of object that owns the trigger
  object_id: The id for that object
  matcher: A function to match StackItems
  function: The function to put on the stack when the matcher is matched
  tags: tags to describe the function
  """
  object_class = ndb.StringProperty()
  object_id = ndb.IntegerProperty()
  matcher = ndb.StringProperty()
  delete_matcher = ndb.StringProperty()
  function = ndb.StringProperty()
  tags = ndb.StringProperty(repeated=True)


###########
# Logging #
###########


class GameLogEvent(ndb.Model):
  stack_item = ndb.StringProperty()
  changes = ndb.StringProperty(indexed=False)


class GameLog(ndb.Model):
  events = ndb.StructuredProperty(GameLogEvent, repeated=True)


##############
# Game class #
##############


class Game(ndb.Model):
  stack = ndb.LocalStructuredProperty(StackItem, repeated=True)
  proactive_triggers = ndb.LocalStructuredProperty(Trigger, repeated=True)
  reactive_triggers = ndb.LocalStructuredProperty(Trigger, repeated=True)
  player_clients = ndb.LocalStructuredProperty(comm.PlayerClient, repeated=True)

  # Used to make sure logs are synced with the game state.
  prev_ts = ndb.DateTimeProperty()
  ts = ndb.DateTimeProperty()

  def Save(self):
    self.put()

  #########
  # Stack #
  #########

  def StopWaiting(self):
    if '__awaiting_input' in self.stack[-1].tags:
      return self.stack.pop()

  def FillWaitingArgs(self, args):
    """Fill in arguments in the stack items that need them.
    FIXME
    GenericProperty (our Args container) can't hold arrays, so if we use
    args to send the options to the client, we can't store other information
    in the args. So that information maybe needs to go in the tags?

    This is a somewhat questionable approach, but should probably work?

    TODO:
    This should probably also provide a mechanism for checking that all
    request arguments get filled.
    """
    if self.stack[-1].function == 'RequestSelection':
      # This is a kludge to allow one endpoint to work for both the use cases of...
      # -> here: The client selecting from an explicitly provided set of options
      request_item = self.stack.pop()
      for t in request_item.tags:
        if t.startswith('index:'):
          index = int(t.split(':')[1])
        if t.startswith('stack_id:'):
          stack_id = int(t.split(':')[1])
      self._FillArg(stack_id, index, args[0])
      return
    elif '__awaiting_input' in self.stack[-1].tags:
      # -> and here: The client more generally filling in the needed arguments.
      self.stack[-1].args = args
      self.stack[-1].tags.remove('__awaiting_input')

  def _FillArg(self, stack_id, index, arg):
    """Fill in one argument in the stack items with the matching stack_id."""
    for stack_item in reversed(self.stack):
      if stack_item.owner_class == 'StackItem' and stack_item.owner_id == stack_id:
        if arg == '__cancel':
          stack_item.tags.append('__cancelled')
        else:
          if not stack_item.args[index]:  # Only fill empty arguments.
            stack_item.args[index] = arg

  def Push(self, function, args=None, tags=None, owner_class=None, owner_id=None):
    if args is None: args = []
    if tags is None: tags = []
    stack_item = StackItem(function=function, args=args, tags=tags, owner_class=owner_class, owner_id=owner_id)
    self.stack.append(stack_item)

    # TODO: Come up with with a good solution for the kind of trigger that's
    #    'When you would do X, do XYX' so that it doesn't immediately expand into
    #    'do XYXYX' -> 'do XYXYXYX', etc.
    # This approach relies on CleanTriggers to try to prevent such a thing, but
    # it's pretty sloppy.
    matched = self.CheckTriggers(self.proactive_triggers, stack_item)
    self.proactive_triggers = self.CleanTriggers(self.proactive_triggers, stack_item)
    self.Do(matched)
    return stack_item

  def Do(self, push_list):
    """Push a list of StackItems to be popped in the order given."""
    for args in reversed(push_list):
      self.Push(*args)

  def CheckTriggers(self, trigger_list, stack_item, changes=None):
    """Check whether any triggers from the list should fire from stack_item.

    TODO: It may be cleaner to return StackItems.

    Args:
      stack_item: StackItem
      trigger_list: list of Trigger

    Returns: a list of tuples
             (function_name (str), args, tags (list of str), object_class, object_id)
             which can be passed to Do.
    """
    if changes is None:
      changes = []
    triggered = []
    for trigger in trigger_list:
      try:
        is_matched, matcher_return = getattr(self, trigger.matcher)(
            trigger.object_class,
            trigger.object_id,
            stack_item,
            changes)
      except:
        logging.error("Error in %s" % trigger.matcher)
        raise
      if is_matched:
        # Passing only the return value from the matcher might make it harder to
        # reuse matchers, but it makes writing the triggered functions cleaner.
        # TODO(eventually): think about a way to make matchers more reusable
        #     Always returning the trigger object is maybe a good start?
        #     Maybe triggers could store args, instead of relying on the matcher.
        triggered.append((trigger.function,
                          matcher_return,
                          trigger.tags,
                          trigger.object_class,
                          trigger.object_id))
    return triggered

  def CleanTriggers(self, trigger_list, stack_item, changes=None):
    if changes is None:
      changes = []
    kept = []
    for trigger in trigger_list:
      if trigger.delete_matcher:
        is_deleted, _ = getattr(self, trigger.delete_matcher)(
            trigger.object_class,
            trigger.object_id,
            stack_item,
            changes)
        if not is_deleted:
          kept.append(trigger)
      else:
        kept.append(trigger)
    return kept

  def RunStackItem(self, stack_item):
    changes = getattr(self, stack_item.function)(*stack_item.args)
    if changes is None: changes = []
    return changes

  def ProcessStack(self):
    """Processes items off the top of the stack until input is required.

    __awaiting_input StackItems can be waiting for args to be filled in or
    even be a blank "blocker" item.

    Returns: a list of state changes
    """
    self.prev_ts = self.ts
    self.ts = datetime.datetime.utcnow()
    events_and_changes = []
    accepted_plies = None
    select_options = None
    while self.stack and '__awaiting_input' not in self.stack[-1].tags:
      stack_item = self.stack.pop()

      # Your game functions can simply remove items from the stack,
      # but it may be safer to simply cancel them instead.
      if '__cancelled' in stack_item.tags:
        continue

      # For watching the stack:
      # logging.debug('STACK %s called with %s', stack_item.function, stack_item.args)
      new_changes = self.RunStackItem(stack_item)

      # TODO: Allow custom handling of simultaneous triggers.
      self.Do(self.CheckTriggers(self.reactive_triggers, stack_item, new_changes))
      events_and_changes.append((stack_item.function,
                                 stack_item.owner_class,
                                 stack_item.owner_id,
                                 new_changes))
      self.reactive_triggers = self.CleanTriggers(self.reactive_triggers, stack_item)
    self.Save()

    # This should probably move into MessageForPlayer.
    # Also, these cases should be made more similar or more different.
    if self.stack and self.stack[-1].function == 'AcceptPly':
      accepted_plies = self.stack[-1].args
    elif self.stack and self.stack[-1].function == 'RequestSelection':
      accepted_plies = ['SelectPly']
      select_options = self.stack[-1].args
    elif self.stack and '__awaiting_input' in self.stack[-1].tags:
      # accepted_plies = ['SelectPly']  Should this be a thing?
      select_options = self.stack[-1].args
    return events_and_changes, accepted_plies, select_options

  #######################
  # State communication #
  #######################

  def GlobalStates(self):
    """Game states visible to all players, to be sent with each change."""
    timestamps = {}
    if self.prev_ts:
      timestamps['__prev_ts'] = self.prev_ts.isoformat()
    if self.ts:
      timestamps['__ts'] = self.ts.isoformat()
    return timestamps

  def PlayerStates(self, player_id):
    """Game states visible to a player, to be sent with each change.

    You should overwrite this in your game, if you need it."""
    return {}

  def MessageForPlayer(self, events_and_changes, accepted_plies, options, player_id):
    """Returns a list of changes to send to the player.

    ...hopefully in the order they happened.
    """
    # TODO: Change identification to deal with
    #         distinguishing identical looking changes
    #         noticing duplicate changes being sent
    #         noticing missing changes
    message = self.GlobalStates()
    message.update(self.PlayerStates(player_id))
    change_list = []
    for (event, owner_class, owner_id, changes) in events_and_changes:
      event_changes = []
      for change in changes:
        cfp = change.ChangeForPlayer(player_id)
        if cfp is not None:
          event_changes.append({'type': change.change_type, 'change': cfp})
      change_item = {'game_event': event, 'changes': event_changes}
      if owner_class:
        change_item['owner'] = [owner_class, owner_id]
      change_list.append(change_item)
    message['game_events'] = change_list
    if self.stack and '__awaiting_input' in self.stack[-1].tags:
      awaited_players = None
      for tag in self.stack[-1].tags:
        if tag.startswith('__waiting_on:'):
          awaited_players = [int(i) for i in tag.split(':')[1].split(',')]
      if awaited_players and player_id not in awaited_players:
        return message
      if accepted_plies:
        message['plies'] = accepted_plies
      if options:
        message['options'] = options
    return message

