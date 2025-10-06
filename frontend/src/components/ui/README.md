# Action Components

This directory contains reusable action components for consistent user interface patterns across the application.

## Components

### ActionDropdown

A flexible dropdown component for displaying action menus.

#### Props

- `actions: ActionItem[]` - Array of action items to display
- `triggerText?: string` - Text for the trigger button (default: "Actions")
- `triggerIcon?: string` - Icon for the trigger button (default: "⋮")
- `className?: string` - Additional CSS classes
- `size?: 'sm' | 'md' | 'lg'` - Size of the dropdown (default: "md")

#### ActionItem Interface

```typescript
interface ActionItem {
  label: string;           // Display text
  onClick: () => void;     // Click handler
  icon?: string;           // Optional icon (emoji or text)
  variant?: 'default' | 'primary' | 'secondary' | 'success' | 'warning' | 'danger';
  disabled?: boolean;      // Whether the action is disabled
}
```

#### Usage Examples

```tsx
import ActionDropdown from '../components/ui/ActionDropdown';

// Basic usage
<ActionDropdown
  actions={[
    {
      label: 'Edit',
      onClick: () => handleEdit(),
      icon: '✏️',
      variant: 'primary'
    },
    {
      label: 'Delete',
      onClick: () => handleDelete(),
      icon: '🗑️',
      variant: 'danger'
    }
  ]}
/>

// Custom trigger
<ActionDropdown
  triggerText="Options"
  triggerIcon="⚙️"
  actions={actions}
  size="sm"
/>
```

### TableActionColumn

A specialized component for table action columns with consistent styling.

#### Props

- `actions: ActionItem[]` - Array of action items
- `className?: string` - Additional CSS classes
- `size?: 'sm' | 'md' | 'lg'` - Size of the dropdown
- `align?: 'left' | 'center' | 'right'` - Alignment of the column (default: "right")

#### Usage Example

```tsx
import TableActionColumn from '../components/ui/TableActionColumn';

// In a table row
<tr>
  <td>Name</td>
  <td>Description</td>
  <TableActionColumn
    actions={[
      {
        label: 'View',
        onClick: () => navigate(`/item/${id}`),
        icon: '👁️',
        variant: 'primary'
      },
      {
        label: 'Edit',
        onClick: () => navigate(`/item/${id}/edit`),
        icon: '✏️',
        variant: 'secondary'
      },
      {
        label: 'Delete',
        onClick: () => handleDelete(id),
        icon: '🗑️',
        variant: 'danger'
      }
    ]}
  />
</tr>
```

## Design Guidelines

### Action Variants

- `primary` - Blue color, for main actions (Edit, View)
- `secondary` - Gray color, for secondary actions
- `success` - Green color, for positive actions (Activate, Enable)
- `warning` - Yellow color, for caution actions (Playground, Test)
- `danger` - Red color, for destructive actions (Delete, Remove)
- `default` - Default gray color

### Icons

Use emoji icons for consistency:
- ✏️ - Edit
- 🗑️ - Delete
- 👁️ - View
- 🎮 - Playground/Test
- ⚙️ - Settings
- 🔑 - Keys
- 📁 - Files
- 🗄️ - Storage

### Sizing

- `sm` - For compact tables and cards
- `md` - Default size for most use cases
- `lg` - For prominent actions

## Migration Guide

To migrate existing action buttons to the new components:

1. Replace inline action buttons with `ActionDropdown`
2. Use `TableActionColumn` for table action columns
3. Ensure consistent icon usage across similar actions
4. Apply appropriate variants for action types

### Before (Inconsistent)
```tsx
<div className="flex space-x-2">
  <button className="text-blue-600 hover:text-blue-900">Edit</button>
  <button className="text-red-600 hover:text-red-900">Delete</button>
</div>
```

### After (Consistent)
```tsx
<ActionDropdown
  actions={[
    {
      label: 'Edit',
      onClick: handleEdit,
      icon: '✏️',
      variant: 'primary'
    },
    {
      label: 'Delete',
      onClick: handleDelete,
      icon: '🗑️',
      variant: 'danger'
    }
  ]}
/>
``` 