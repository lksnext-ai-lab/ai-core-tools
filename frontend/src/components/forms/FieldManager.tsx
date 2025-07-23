import { useState } from 'react';

interface FieldDefinition {
  name: string;
  type: string;
  description: string;
  parser_id?: number;
  list_item_type?: string;
  list_item_parser_id?: number;
}

interface FieldManagerProps {
  fields: FieldDefinition[];
  onChange: (fields: FieldDefinition[]) => void;
  availableParsers: Array<{value: number, name: string}>;
  maxFields?: number;
}

function FieldManager({ fields, onChange, availableParsers, maxFields = 20 }: FieldManagerProps) {
  const fieldTypes = [
    { value: 'str', name: 'String' },
    { value: 'int', name: 'Integer' },
    { value: 'float', name: 'Float' },
    { value: 'bool', name: 'Boolean' },
    { value: 'date', name: 'Date' },
    { value: 'list', name: 'List' },
    { value: 'parser', name: 'Parser Reference' }
  ];

  const addField = () => {
    if (fields.length >= maxFields) return;
    
    const newField: FieldDefinition = {
      name: '',
      type: 'str',
      description: ''
    };
    
    onChange([...fields, newField]);
  };

  const removeField = (index: number) => {
    const newFields = fields.filter((_, i) => i !== index);
    onChange(newFields);
  };

  const updateField = (index: number, updates: Partial<FieldDefinition>) => {
    const newFields = fields.map((field, i) => {
      if (i === index) {
        const updatedField = { ...field, ...updates };
        
        // Clear type-specific fields when type changes
        if (updates.type && updates.type !== field.type) {
          if (updates.type !== 'parser') {
            updatedField.parser_id = undefined;
          }
          if (updates.type !== 'list') {
            updatedField.list_item_type = undefined;
            updatedField.list_item_parser_id = undefined;
          }
        }
        
        return updatedField;
      }
      return field;
    });
    
    onChange(newFields);
  };

  const validateFieldName = (name: string): boolean => {
    const pattern = /^[a-zA-Z0-9_]+$/;
    return pattern.test(name);
  };

  const getListItemTypes = () => [
    { value: 'str', name: 'String' },
    { value: 'int', name: 'Integer' },
    { value: 'float', name: 'Float' },
    { value: 'bool', name: 'Boolean' },
    { value: 'date', name: 'Date' },
    { value: 'parser', name: 'Parser Reference' }
  ];

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-medium text-gray-900">Fields ({fields.length}/{maxFields})</h3>
        <button
          type="button"
          onClick={addField}
          disabled={fields.length >= maxFields}
          className="px-3 py-1 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white text-sm rounded transition-colors"
        >
          Add Field
        </button>
      </div>

      {/* Fields Table */}
      {fields.length > 0 ? (
        <div className="border border-gray-300 rounded-lg overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-1/4">
                  Field Name
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-1/3">
                  Type & Configuration
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-1/3">
                  Description
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-16">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {fields.map((field, index) => (
                <tr key={index} className="hover:bg-gray-50">
                  <td className="px-6 py-4 align-top">
                    <input
                      type="text"
                      value={field.name}
                      onChange={(e) => updateField(index, { name: e.target.value })}
                      className={`w-full px-3 py-2 border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                        field.name && !validateFieldName(field.name) 
                          ? 'border-red-300 bg-red-50' 
                          : 'border-gray-300'
                      }`}
                      placeholder="field_name"
                    />
                    {field.name && !validateFieldName(field.name) && (
                      <p className="text-xs text-red-600 mt-1">
                        Only letters, numbers, and underscores
                      </p>
                    )}
                  </td>
                  
                  <td className="px-6 py-4 align-top">
                    <div className="space-y-3">
                      {/* Main Type Selector */}
                      <select
                        value={field.type}
                        onChange={(e) => updateField(index, { type: e.target.value })}
                        className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      >
                        {fieldTypes.map((type) => (
                          <option key={type.value} value={type.value}>
                            {type.name}
                          </option>
                        ))}
                      </select>
                      
                      {/* Parser Reference Selector */}
                      {field.type === 'parser' && (
                        <div>
                          <label className="block text-xs font-medium text-gray-700 mb-1">
                            Reference Parser:
                          </label>
                          <select
                            value={field.parser_id || ''}
                            onChange={(e) => updateField(index, { parser_id: parseInt(e.target.value) || undefined })}
                            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                          >
                            <option value="">Select parser...</option>
                            {availableParsers.map((parser) => (
                              <option key={parser.value} value={parser.value}>
                                {parser.name}
                              </option>
                            ))}
                          </select>
                        </div>
                      )}
                      
                      {/* List Type Selectors */}
                      {field.type === 'list' && (
                        <div className="space-y-2">
                          <label className="block text-xs font-medium text-gray-700 mb-1">
                            List Item Type:
                          </label>
                          <select
                            value={field.list_item_type || 'str'}
                            onChange={(e) => updateField(index, { list_item_type: e.target.value })}
                            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                          >
                            {getListItemTypes().map((type) => (
                              <option key={type.value} value={type.value}>
                                {type.name}
                              </option>
                            ))}
                          </select>
                          
                          {field.list_item_type === 'parser' && (
                            <div>
                              <label className="block text-xs font-medium text-gray-700 mb-1">
                                List Item Parser:
                              </label>
                              <select
                                value={field.list_item_parser_id || ''}
                                onChange={(e) => updateField(index, { list_item_parser_id: parseInt(e.target.value) || undefined })}
                                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                              >
                                <option value="">Select parser...</option>
                                {availableParsers.map((parser) => (
                                  <option key={parser.value} value={parser.value}>
                                    {parser.name}
                                  </option>
                                ))}
                              </select>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </td>
                  
                  <td className="px-6 py-4 align-top">
                    <textarea
                      value={field.description}
                      onChange={(e) => updateField(index, { description: e.target.value })}
                      rows={3}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                      placeholder="Describe this field..."
                    />
                  </td>
                  
                  <td className="px-6 py-4 align-top">
                    <button
                      type="button"
                      onClick={() => removeField(index)}
                      className="text-red-600 hover:text-red-900 transition-colors p-2"
                      title="Remove field"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                      </svg>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="text-center py-8 border-2 border-dashed border-gray-300 rounded-lg">
          <p className="text-gray-500 mb-4">No fields defined yet</p>
          <button
            type="button"
            onClick={addField}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
          >
            Add First Field
          </button>
        </div>
      )}

      {/* Field Types Help */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
        <h4 className="text-sm font-medium text-blue-800 mb-2">Field Types Reference</h4>
        <div className="text-xs text-blue-700 space-y-1">
          <p><strong>String:</strong> Text data (e.g., "hello world")</p>
          <p><strong>Integer:</strong> Whole numbers (e.g., 42)</p>
          <p><strong>Float:</strong> Decimal numbers (e.g., 3.14)</p>
          <p><strong>Boolean:</strong> True/False values</p>
          <p><strong>Date:</strong> Date values (e.g., 2024-01-15)</p>
          <p><strong>List:</strong> Array of items with specified type</p>
          <p><strong>Parser Reference:</strong> Reference to another data structure</p>
        </div>
      </div>
    </div>
  );
}

export default FieldManager; 