# Apple Reminders JXA (JavaScript for Automation) API Documentation

## Overview

This document describes the JXA (JavaScript for Automation) API for interacting with Apple Reminders.app on macOS. JXA is Apple's JavaScript implementation for automating macOS applications via AppleScript/Open Scripting Architecture (OSA).

## Current State of JXA (2024-2025)

Based on research, JXA has the following characteristics:

- **Status**: JXA is considered "dead tech walking" as the Mac Automation team has disbanded
- **Documentation**: Limited and scattered; Apple has not actively developed JXA since its introduction
- **Stability**: Despite lack of development, JXA continues to work on macOS Sonoma and later versions
- **Alternatives**: AppleScript remains the most reliable option; Swift EventKit provides native access but with different capabilities

### Known Limitations

1. **No direct move operations**: JXA cannot construct insertion location specifiers, making it impossible to directly move reminders between lists. Workaround: recreate the reminder in the target list and delete the original.
2. **No list deletion**: Neither JXA nor AppleScript supports deleting reminder lists directly
3. **No HTTP requests**: JXA cannot perform HTTP requests directly
4. **Limited documentation**: The scripting dictionary is the primary reference

## Scripting Dictionary Reference

### Application Properties

| Property | Type | Access | Description |
|----------|------|--------|-------------|
| `defaultAccount` | Account | read | The account currently active in Reminders |
| `defaultList` | List | read | The list currently active in Reminders |

### List Class

Lists are containers for reminders.

| Property | Code | Type | Access | Description |
|----------|------|------|--------|-------------|
| `id` | ID | text | read-only | Unique identifier of the list |
| `name` | pnam | text | read/write | Name of the list |
| `container` | cntr | Account | read-only | The account containing the list |
| `color` | colr | text | read/write | List color |
| `emblem` | emblm | text | read/write | List emblem/icon |

### Reminder Class

Reminders are individual items within a list.

| Property | Code | Type | Access | Description |
|----------|------|------|--------|-------------|
| `id` | ID | text | read-only | Unique identifier (format: `x-apple-reminder://UUID`) |
| `name` | pnam | text | read/write | Title of the reminder |
| `body` | body | text | read/write | Notes/description |
| `completed` | comb | boolean | read/write | Completion status |
| `completionDate` | comd | date | read/write | When reminder was completed |
| `creationDate` | ascd | date | read-only | When reminder was created |
| `modificationDate` | asmo | date | read-only | When reminder was last modified |
| `dueDate` | dued | date | read/write | Due date (all-day or specific time) |
| `remindMeDate` | rmdt | date | read/write | Alert/notification time |
| `priority` | prio | integer | read/write | Priority level (see below) |
| `container` | cntr | List | read-only | The list containing the reminder |

### Priority Levels

| Value | Level |
|-------|-------|
| 0 | None |
| 1-4 | Low |
| 5 | Medium |
| 6-9 | High |

## JXA API Usage

### Basic Setup

```javascript
// Get the Reminders application
const Reminders = Application('Reminders');
```

### List Operations

#### Get All Lists

```javascript
const lists = Reminders.lists();
lists.forEach(list => {
    console.log(list.id(), list.name());
});
```

#### Get List by Name

```javascript
const list = Reminders.lists.byName('My List');
```

#### Create a New List

```javascript
const newList = Reminders.List({ name: 'New List' });
Reminders.lists.push(newList);
```

#### Get Default List

```javascript
const defaultList = Reminders.defaultList();
```

### Reminder Operations

#### Get All Reminders from a List

```javascript
const list = Reminders.lists.byName('My List');
const reminders = list.reminders();

reminders.forEach(reminder => {
    console.log({
        id: reminder.id(),
        name: reminder.name(),
        body: reminder.body(),
        completed: reminder.completed(),
        dueDate: reminder.dueDate(),
        priority: reminder.priority()
    });
});
```

#### Filter Reminders with `whose`

```javascript
// Get only incomplete reminders
const incompleteReminders = list.reminders.whose({ completed: false })();

// Get reminders by name
const namedReminders = list.reminders.whose({ name: 'Specific Name' })();

// Complex queries with _and, _or, _not
const filtered = list.reminders.whose({
    _and: [
        { completed: false },
        { priority: { '>': 0 } }
    ]
})();
```

#### Create a Reminder

```javascript
const newReminder = Reminders.Reminder({
    name: 'My Reminder',
    body: 'Notes for the reminder',
    dueDate: new Date('2025-12-27T10:00:00'),
    remindMeDate: new Date('2025-12-27T10:00:00'),
    priority: 5
});
list.reminders.push(newReminder);
```

#### Update a Reminder

```javascript
const reminders = list.reminders.whose({ name: 'My Reminder' })();
if (reminders.length > 0) {
    const reminder = reminders[0];
    reminder.name = 'Updated Name';
    reminder.body = 'Updated notes';
    reminder.completed = true;
    reminder.priority = 9;
    reminder.dueDate = new Date('2025-12-28T14:00:00');
}
```

#### Delete a Reminder

```javascript
const reminders = list.reminders.whose({ name: 'My Reminder' })();
if (reminders.length > 0) {
    Reminders.delete(reminders[0]);
}
```

#### Move a Reminder Between Lists (Workaround)

Since JXA cannot directly move reminders, use this workaround:

```javascript
function moveReminder(fromListName, reminderName, toListName) {
    const fromList = Reminders.lists.byName(fromListName);
    const toList = Reminders.lists.byName(toListName);

    const reminders = fromList.reminders.whose({ name: reminderName })();
    if (reminders.length === 0) return null;

    const oldReminder = reminders[0];

    // Copy properties
    const props = {
        name: oldReminder.name(),
        body: oldReminder.body() || undefined,
        completed: oldReminder.completed(),
        priority: oldReminder.priority()
    };

    if (oldReminder.dueDate()) {
        props.dueDate = oldReminder.dueDate();
    }
    if (oldReminder.remindMeDate()) {
        props.remindMeDate = oldReminder.remindMeDate();
    }

    // Create in new list
    const newReminder = Reminders.Reminder(props);
    toList.reminders.push(newReminder);

    // Delete from old list
    Reminders.delete(oldReminder);

    return newReminder;
}
```

## Command-Line Usage

The script at `src/jxa/reminders.js` provides a CLI interface:

```bash
# Get help
osascript -l JavaScript src/jxa/reminders.js help

# List all reminder lists
osascript -l JavaScript src/jxa/reminders.js listLists

# Get all reminders from a list
osascript -l JavaScript src/jxa/reminders.js getReminders "My List"

# Get only incomplete reminders
osascript -l JavaScript src/jxa/reminders.js getIncompleteReminders "My List"

# Create a reminder
osascript -l JavaScript src/jxa/reminders.js createReminder "My List" "Reminder Name" "Notes" "2025-12-27T10:00:00" 5

# Update a reminder property
osascript -l JavaScript src/jxa/reminders.js updateReminder "My List" "Reminder Name" body "New notes"

# Delete a reminder
osascript -l JavaScript src/jxa/reminders.js deleteReminder "My List" "Reminder Name"

# Delete a reminder by ID
osascript -l JavaScript src/jxa/reminders.js deleteReminderById "x-apple-reminder://UUID"

# Move a reminder between lists
osascript -l JavaScript src/jxa/reminders.js moveReminder "Source List" "Reminder Name" "Destination List"

# Get a reminder by ID
osascript -l JavaScript src/jxa/reminders.js getReminderById "x-apple-reminder://UUID"

# Create a new list
osascript -l JavaScript src/jxa/reminders.js createList "New List Name"

# Get default list
osascript -l JavaScript src/jxa/reminders.js getDefaultList
```

## Important Notes

### Date Handling

- Dates should be passed as ISO 8601 strings (e.g., `2025-12-27T10:00:00`)
- The system converts to local timezone
- Setting `dueDate` creates an all-day reminder unless time is specified
- Setting `remindMeDate` creates a notification at that time

### Object Specifiers vs Values

In JXA, accessing properties returns Object Specifiers, not actual values. To get the value, call the property as a function:

```javascript
// Object Specifier (not useful)
reminder.name    // Returns ObjectSpecifier

// Actual value
reminder.name()  // Returns "Reminder Name"
```

### Error Handling

All operations can throw errors. Common error scenarios:
- List not found
- Reminder not found
- Permission denied (requires Reminders access in System Settings > Privacy & Security)

### Permissions

The script requires Reminders access permission. On first run, macOS will prompt for permission. If denied, operations will fail.

## Alternative Tools

### reminders-cli (by keith)

A Swift-based CLI tool with more features:
- Natural language date parsing
- JSON output format
- Priority levels
- Notification support

GitHub: https://github.com/keith/reminders-cli

### node-reminders

An npm package wrapping JXA scripts:
- TypeScript support
- Promise-based API
- Easy integration with Node.js projects

npm: https://www.npmjs.com/package/node-reminders

## References

- [JXA Examples](https://jxa-examples.akjems.com/)
- [JXA Scripting Dictionary Guide](https://bru6.de/jxa/basics/scripting-dictionary/)
- [Reminders.sdef (Scripting Dictionary)](https://github.com/JXA-userland/JXA/blob/master/packages/@jxa/types/tools/sdefs/Reminders.sdef)
- [Apple Developer Forums - JXA Discussion](https://developer.apple.com/forums/thread/649653)
- [reminders-cli GitHub](https://github.com/keith/reminders-cli)
- [node-reminders npm](https://www.npmjs.com/package/node-reminders)
