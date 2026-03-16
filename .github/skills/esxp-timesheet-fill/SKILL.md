---
name: esxp-timesheet-fill
description: 'Automate timesheet logging on the ESXP (Enterprise Services Experience) platform. Use when asked to "fill timesheet", "log hours", "submit labor entry", "enter time in ESXP", "update timesheet", "log work hours", "fill ESXP time", "weekly time entry", or when automating labor entries on esxp.microsoft.com. Supports navigating the week view, selecting days, choosing support packages, setting hours, adding notes, and submitting entries.'
---

# ESXP Timesheet Fill

Automates labor/time entry on the Microsoft ESXP (Enterprise Services Experience) platform at `https://esxp.microsoft.com/#/time/weekview`. This skill drives the browser to navigate the week view, select days, open labor entry forms, choose packages from recent entries, set hours, add customer notes, and submit.

## When to Use This Skill

- User asks to fill or update their ESXP timesheet
- User wants to log hours for one or more days of the week
- User asks to submit labor entries for support packages
- User wants to automate repetitive weekly time entry
- User mentions ESXP, labor entry, or week view time logging

## Prerequisites

- Browser automation tool (e.g. `browse_web`) must be available
- User must be authenticated to `esxp.microsoft.com` (SSO session active in browser)
- The target week and package details should be known or provided by the user

## Step-by-Step Workflow

### Step 1: Navigate to ESXP Week View

Navigate to the ESXP labor entry week view and wait for full page load.

```
URL: https://esxp.microsoft.com/#/time/weekview
Expected page title: "Labor Entry - Week View"
```

- Use `browse_web` navigate action with URL `https://esxp.microsoft.com/#/time/weekview` and a generous timeout (60s).
- The page may initially redirect to the home page. If the title is "Home" instead of "Labor Entry - Week View", retry the navigation.
- Take a screenshot to confirm the page loaded correctly and identify the current week displayed.

### Step 2: Expand the Day Carousel

Click the date carousel button to reveal individual day selectors.

```
Selector: .carousel-date-btn
```

- Click the element with class `carousel-date-btn` to expand the day picker.
- The carousel shows all days of the current week (Sunday–Saturday) with hours logged per day.

### Step 3: Select the Target Day

Click the specific day button in the carousel.

```
Selector: .carousel-date-btn:has-text("<DayName>")
Example:  .carousel-date-btn:has-text("Monday")
```

- Replace `<DayName>` with the target day (e.g., "Monday", "Tuesday", etc.).
- After clicking, the selected day will be highlighted with a blue border and the view will update to show that day's entries.
- Repeat Steps 3–7 for each day that needs hours logged.

### Step 4: Open the Labor Entry Form

Click the **+** (add) button next to the "SUPPORT PACKAGES" section.

```
Selector: button[aria-label="Click here to enter single or bulk labor for support packages"]
```

- This opens a labor submission form panel on the right side.
- The form includes fields for: Search By, Name/Alias, Package, Category, Timezone, Hours/Minutes, and Customer Notes.
- The user's alias (e.g., "nadeemis") is typically pre-filled.

### Step 5: Select the Package from Recent Entries

Click on the desired package under the "RECENT ENTRIES" section in the form.

```
Selector: text=<PackageName>
Example:  text=CAIP-IPDEV-APP
```

- Replace `<PackageName>` with the target package name.
- The form fields (Package, Category) will auto-populate after selection.

### Step 6: Set the Hours

Click the hour increment button the required number of times.

```
Selector: button[aria-label="Increment by 1 Hour"]
```

- Click this button N times where N = desired hours (e.g., 4 clicks for 4 hours).
- Both "Actual Labor" and "Charged Labor" fields will update to show the total.
- For minutes, use `button[aria-label="Increment by 15 Minutes"]` if needed.

### Step 7: Add Customer Notes and Submit

Fill in the optional customer notes field and click Update.

```
Notes selector: textarea[aria-label="Customer Notes. Word limit 500 Characters max - Optional field"]
Submit selector: button:has-text("Update")
```

- Use `browse_web` fill action on the textarea with the desired note text (e.g., "#IPDEV #Contelligence").
- Click the "Update" button to submit the labor entry.
- The form will close and the week view will reflect the updated hours for that day.

### Step 8: Repeat for Additional Days

If logging hours for multiple days in the week:

1. Return to **Step 3** and select the next day.
2. Repeat Steps 4–7 for each additional day.
3. After all days are complete, take a final screenshot to confirm the week totals.

### Step 9: Save Timesheet as Draft

After filling all entries, click the "Save As Draft" button to save the timesheet without submitting for approval.

```
Selector: button:has-text("Save As Draft")
```

## **NEVER** click the "Agree & Submit All" button, as this will send the timesheet for approval. Always use "Save As Draft" to avoid unintended submission.



## Default Values (Customizable)

| Parameter | Default | Description |
|-----------|---------|-------------|
| Package | `CAIP-IPDEV-APP` | Support package from recent entries |
| Hours per day | `4` | Number of hours to log per day |
| Customer Notes | `#IPDEV #Contelligence` | Note text for each entry |
| Days | Monday–Friday | Weekdays to fill |

Users can override any of these defaults by specifying them in their prompt.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Page redirects to Home | Retry navigation to the weekview URL; SSO may need a moment to resolve |
| Carousel not expanding | Ensure `.carousel-date-btn` selector is correct; take a screenshot to inspect |
| Package not in recent entries | Use the search field instead: fill the "Enter Name or Alias" input and select from the dropdown |
| Hours not incrementing | Verify the `aria-label` attribute on the increment button; take a screenshot to debug |
| Update button not responding | Ensure all required fields are filled; check for validation errors on the form |
| Wrong week displayed | Use the week navigation arrows to move to the correct week before selecting days |

## Example Prompts

- "Fill my ESXP timesheet for this week with 4 hours per day on CAIP-IPDEV-APP"
- "Log 8 hours on Monday and Tuesday for CAIP-IPDEV-APP with notes #IPDEV"
- "Submit my ESXP labor entry for today, 4 hours, package CAIP-IPDEV-APP"
- "Fill timesheet Monday through Friday, 4 hours each day"
