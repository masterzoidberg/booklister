# BookLister AI - Output Rules

## Formatting Requirements

### Title Box
```
[Title: Your 80-character title here]
```
- Must be exactly 80 characters or less
- Include character count outside box: (XX/80)
- Place outside the box, not inside

### Description Box
```
[Description: Your compelling 2-3 paragraph description here]
```
- Clear, concise, buyer-focused
- Highlight condition and key features

### Item Specifics Boxes
Each specific gets its own box:
```
[Features: Feature1;Feature2;Feature3]
[Topic: Main subject area]
[Genre: Book category]
```
- Use semicolons to separate multiple values
- One box per specific type

## Validation Rules
- Title must be ≤ 80 characters
- All boxes must have proper labels
- Labels go OUTSIDE the boxes
- No labels inside the content boxes
- Character count goes outside title box
- Use semicolons for multi-value fields

## Example Correct Format
```
[Title: The Great Gatsby by F. Scott Fitzgerald - Very Good Cond]
(65/80)

[Description: This classic American novel is in very good condition with minimal wear. The pages are clean and unmarked, with a tight binding. A beautiful edition perfect for collectors and students alike.]

[Features: Classic American Literature;1920s Fiction;Collector's Edition]
[Topic: Literature]
[Genre: Fiction]
```

## Common Errors to Avoid
- ❌ [Title: Book title (65/80)] - count inside box
- ❌ Title: Book title (65/80) - missing box
- ❌ [Features: Item1, Item2, Item3] - wrong separator
- ✅ [Features: Item1;Item2;Item3] - correct format