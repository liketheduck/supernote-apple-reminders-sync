#!/usr/bin/env swift

/**
 * Reminder Helper - Fast EventKit operations for fields reminders-cli doesn't support
 *
 * Usage:
 *   swift reminder-helper.swift set-due-date <list> <id> <iso-date|null>
 *   swift reminder-helper.swift set-priority <list> <id> <0-9>
 *   swift reminder-helper.swift move <from-list> <id> <to-list>
 *
 * Much faster than JXA because it uses native EventKit directly.
 */

import EventKit
import Foundation

let store = EKEventStore()

func requestAccess() -> Bool {
    var granted = false
    let semaphore = DispatchSemaphore(value: 0)

    if #available(macOS 14.0, *) {
        store.requestFullAccessToReminders { success, error in
            granted = success
            semaphore.signal()
        }
    } else {
        store.requestAccess(to: .reminder) { success, error in
            granted = success
            semaphore.signal()
        }
    }

    _ = semaphore.wait(timeout: .distantFuture)
    return granted
}

func getCalendar(name: String) -> EKCalendar? {
    let calendars = store.calendars(for: .reminder)
    return calendars.first { $0.title == name }
}

func getReminder(listName: String, id: String) -> EKReminder? {
    guard let calendar = getCalendar(name: listName) else {
        fputs("Error: List '\(listName)' not found\n", stderr)
        return nil
    }

    let predicate = store.predicateForReminders(in: [calendar])
    var foundReminder: EKReminder?
    let semaphore = DispatchSemaphore(value: 0)

    store.fetchReminders(matching: predicate) { reminders in
        foundReminder = reminders?.first { reminder in
            reminder.calendarItemExternalIdentifier == id ||
            reminder.calendarItemIdentifier == id
        }
        semaphore.signal()
    }

    _ = semaphore.wait(timeout: .distantFuture)
    return foundReminder
}

func setDueDate(listName: String, id: String, dateStr: String) -> Bool {
    guard let reminder = getReminder(listName: listName, id: id) else {
        fputs("Error: Reminder with ID '\(id)' not found in '\(listName)'\n", stderr)
        return false
    }

    if dateStr == "null" || dateStr.isEmpty {
        reminder.dueDateComponents = nil
    } else {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

        if let date = formatter.date(from: dateStr) {
            reminder.dueDateComponents = Calendar.current.dateComponents(
                [.year, .month, .day, .hour, .minute, .second],
                from: date
            )
        } else {
            // Try without fractional seconds
            formatter.formatOptions = [.withInternetDateTime]
            if let date = formatter.date(from: dateStr) {
                reminder.dueDateComponents = Calendar.current.dateComponents(
                    [.year, .month, .day, .hour, .minute, .second],
                    from: date
                )
            } else {
                // Try Python isoformat without timezone (assume local)
                let localFormatter = DateFormatter()
                // Try with microseconds first
                localFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS"
                localFormatter.timeZone = .current
                if let date = localFormatter.date(from: dateStr) {
                    reminder.dueDateComponents = Calendar.current.dateComponents(
                        [.year, .month, .day, .hour, .minute, .second],
                        from: date
                    )
                } else if let date = { () -> Date? in
                    localFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
                    return localFormatter.date(from: dateStr)
                }() {
                    reminder.dueDateComponents = Calendar.current.dateComponents(
                        [.year, .month, .day, .hour, .minute, .second],
                        from: date
                    )
                } else {
                    // Try date-only format
                    localFormatter.dateFormat = "yyyy-MM-dd"
                    if let date = localFormatter.date(from: dateStr) {
                        reminder.dueDateComponents = Calendar.current.dateComponents(
                            [.year, .month, .day],
                            from: date
                        )
                    } else {
                        fputs("Error: Could not parse date '\(dateStr)'\n", stderr)
                        return false
                    }
                }
            }
        }
    }

    do {
        try store.save(reminder, commit: true)
        return true
    } catch {
        fputs("Error saving reminder: \(error.localizedDescription)\n", stderr)
        return false
    }
}

func setPriority(listName: String, id: String, priorityStr: String) -> Bool {
    guard let reminder = getReminder(listName: listName, id: id) else {
        fputs("Error: Reminder with ID '\(id)' not found in '\(listName)'\n", stderr)
        return false
    }

    guard let priority = Int(priorityStr), priority >= 0 && priority <= 9 else {
        fputs("Error: Priority must be 0-9\n", stderr)
        return false
    }

    reminder.priority = priority

    do {
        try store.save(reminder, commit: true)
        return true
    } catch {
        fputs("Error saving reminder: \(error.localizedDescription)\n", stderr)
        return false
    }
}

func moveReminder(fromList: String, id: String, toList: String) -> Bool {
    guard let reminder = getReminder(listName: fromList, id: id) else {
        fputs("Error: Reminder with ID '\(id)' not found in '\(fromList)'\n", stderr)
        return false
    }

    guard let targetCalendar = getCalendar(name: toList) else {
        fputs("Error: Target list '\(toList)' not found\n", stderr)
        return false
    }

    reminder.calendar = targetCalendar

    do {
        try store.save(reminder, commit: true)
        return true
    } catch {
        fputs("Error saving reminder: \(error.localizedDescription)\n", stderr)
        return false
    }
}

// Main
guard requestAccess() else {
    fputs("Error: Reminders access denied\n", stderr)
    exit(1)
}

let args = Array(CommandLine.arguments.dropFirst())
guard args.count >= 1 else {
    print("""
    Usage:
      swift reminder-helper.swift set-due-date <list> <id> <iso-date|null>
      swift reminder-helper.swift set-priority <list> <id> <0-9>
      swift reminder-helper.swift move <from-list> <id> <to-list>
    """)
    exit(1)
}

let command = args[0]
var success = false

switch command {
case "set-due-date":
    guard args.count >= 4 else {
        fputs("Usage: set-due-date <list> <id> <iso-date|null>\n", stderr)
        exit(1)
    }
    success = setDueDate(listName: args[1], id: args[2], dateStr: args[3])

case "set-priority":
    guard args.count >= 4 else {
        fputs("Usage: set-priority <list> <id> <0-9>\n", stderr)
        exit(1)
    }
    success = setPriority(listName: args[1], id: args[2], priorityStr: args[3])

case "move":
    guard args.count >= 4 else {
        fputs("Usage: move <from-list> <id> <to-list>\n", stderr)
        exit(1)
    }
    success = moveReminder(fromList: args[1], id: args[2], toList: args[3])

default:
    fputs("Unknown command: \(command)\n", stderr)
    exit(1)
}

exit(success ? 0 : 1)
