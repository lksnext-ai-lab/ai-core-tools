import { useState } from 'react';

/**
 * Custom hook for managing settings modal state (create/edit)
 * Eliminates repetitive modal state management code
 * 
 * @returns Object containing modal state and control functions
 */
export function useSettingsModal<T>() {
  const [isOpen, setIsOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<T | null>(null);

  /**
   * Open modal in create mode
   */
  const openCreate = () => {
    setEditingItem(null);
    setIsOpen(true);
  };

  /**
   * Open modal in edit mode with existing item
   */
  const openEdit = (item: T) => {
    setEditingItem(item);
    setIsOpen(true);
  };

  /**
   * Close modal and reset editing item
   */
  const close = () => {
    setIsOpen(false);
    setEditingItem(null);
  };

  /**
   * Check if modal is in edit mode
   */
  const isEditing = editingItem !== null;

  return {
    isOpen,
    editingItem,
    isEditing,
    openCreate,
    openEdit,
    close
  };
}

