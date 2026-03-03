# UI Components

This directory contains reusable UI components for consistent user interface patterns across the application.

## Components

### Tabs

A fully accessible, responsive tab navigation component for organizing content into logical sections.

#### Features

- **Keyboard Navigation** — Arrow keys to switch tabs, Home/End to jump to first/last tab
- **Accessible** — Full ARIA labels, semantic HTML, and focus management
- **Responsive** — Adapts to mobile and desktop screens
- **Icon Support** — Optional icons alongside tab labels for enhanced visual recognition
- **State Management** — Simple controlled component pattern with `activeTab` and `onChange`

#### Props

- `tabs: TabItem[]` - Array of tab items to display (required)
- `activeTab: string` - ID of the currently active tab (required)
- `onChange: (tabId: string) => void` - Callback when tab is changed (required)
- `className?: string` - Additional CSS classes for the container

#### TabItem Interface

```typescript
interface TabItem {
  id: string;        // Unique identifier for the tab
  label: string;     // Display label for the tab
  icon?: string;     // Optional icon (emoji or text)
}
```

#### Usage Example

```tsx
import { Tabs } from '../components/ui/Tabs';
import { useState } from 'react';

export function MyComponent() {
  const [activeTab, setActiveTab] = useState<string>('basic');

  const tabs = [
    { id: 'basic', label: 'Basic', icon: '📝' },
    { id: 'prompts', label: 'Prompts', icon: '💬' },
    { id: 'config', label: 'Configuration', icon: '⚙️' },
    { id: 'advanced', label: 'Advanced', icon: '🔧' },
    { id: 'marketplace', label: 'Marketplace', icon: '🛒' },
  ];

  return (
    <div>
      <Tabs
        tabs={tabs}
        activeTab={activeTab}
        onChange={setActiveTab}
      />

      <div className="p-6">
        {activeTab === 'basic' && (
          <div>
            {/* Basic tab content */}
          </div>
        )}
        {activeTab === 'prompts' && (
          <div>
            {/* Prompts tab content */}
          </div>
        )}
        {/* ... other tabs ... */}
      </div>
    </div>
  );
}
```

#### Keyboard Navigation

- **Arrow Right / Arrow Left** — Switch to next/previous tab
- **Home** — Jump to first tab
- **End** — Jump to last tab
- **Enter/Space** — Activate tab (when focused)

#### Accessibility

The component uses semantic HTML and ARIA attributes:
- `role="tablist"` on the container
- `role="tab"` on individual tab buttons
- `aria-selected` indicates active state
- `aria-controls` links tabs to their content panels
- `tabindex` management for keyboard focus
- Focus visible indicator with blue ring

#### Styling

Tab styling uses Tailwind CSS:
- **Active tab**: Blue text (`text-blue-600`) with blue bottom border (`border-blue-600`)
- **Inactive tabs**: Gray text (`text-gray-600`) with transparent border
- **Hover state**: Slightly darker text and light background
- **Focus state**: Blue focus ring for keyboard navigation

#### Best Practices

1. **Tab IDs** — Use meaningful, kebab-case IDs like `basic`, `configuration`, `advanced`
2. **Tab Organization** — Group related settings in 3–6 tabs
3. **Icons** — Optional but recommended for quick visual recognition
4. **Single Form** — All form data stays in parent component state; form submits once from parent
5. **Error Handling** — Display errors in their respective tab sections, not globally
6. **Mobile** — Icons help on small screens where label space is limited

---

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