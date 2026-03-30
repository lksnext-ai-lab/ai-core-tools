import React, { useEffect, useState } from 'react';
import { apiService } from '../../services/api';

interface TierConfigEntry {
  id: number;
  tier: string;
  resource_type: string;
  limit_value: number;
}

const TierConfigPage: React.FC = () => {
  const [configs, setConfigs] = useState<TierConfigEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetch = async () => {
      try {
        const data = await apiService.getTierConfig();
        setConfigs(data as TierConfigEntry[]);
      } catch (err: any) {
        setError(err?.message || 'Failed to load tier config');
      } finally {
        setIsLoading(false);
      }
    };
    fetch();
  }, []);

  const handleSave = async (entry: TierConfigEntry, newValue: number) => {
    const key = `${entry.tier}_${entry.resource_type}`;
    setSaving(key);
    try {
      await apiService.updateTierConfig({
        tier: entry.tier,
        resource_type: entry.resource_type,
        limit_value: newValue,
      });
      setConfigs(prev =>
        prev.map(c => c.id === entry.id ? { ...c, limit_value: newValue } : c)
      );
    } catch (err: any) {
      alert(err?.message || 'Failed to save');
    } finally {
      setSaving(null);
    }
  };

  if (isLoading) return <div className="p-8 text-gray-500">Loading tier config...</div>;
  if (error) return <div className="p-8 text-red-600">{error}</div>;

  const tiers = [...new Set(configs.map(c => c.tier))].sort();

  return (
    <div className="max-w-4xl mx-auto p-8">
      <h1 className="text-2xl font-bold mb-6">Tier Configuration</h1>
      <p className="text-sm text-gray-500 mb-4">Use -1 to indicate unlimited.</p>
      {tiers.map(tier => (
        <div key={tier} className="mb-8">
          <h2 className="text-lg font-semibold capitalize mb-3">{tier}</h2>
          <div className="bg-white border rounded-lg overflow-auto shadow-sm">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
                <tr>
                  <th className="px-4 py-2 text-left">Resource</th>
                  <th className="px-4 py-2 text-right">Limit</th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {configs.filter(c => c.tier === tier).map(entry => (
                  <TierConfigRow
                    key={entry.id}
                    entry={entry}
                    isSaving={saving === `${entry.tier}_${entry.resource_type}`}
                    onSave={handleSave}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
};

const TierConfigRow: React.FC<{
  entry: TierConfigEntry;
  isSaving: boolean;
  onSave: (entry: TierConfigEntry, value: number) => Promise<void>;
}> = ({ entry, isSaving, onSave }) => {
  const [value, setValue] = useState(entry.limit_value);

  return (
    <tr className="hover:bg-gray-50">
      <td className="px-4 py-2">{entry.resource_type.replace(/_/g, ' ')}</td>
      <td className="px-4 py-2 text-right">
        <input
          type="number"
          value={value}
          onChange={e => setValue(Number(e.target.value))}
          className="w-20 border rounded px-2 py-1 text-right"
        />
      </td>
      <td className="px-4 py-2">
        <button
          onClick={() => onSave(entry, value)}
          disabled={isSaving || value === entry.limit_value}
          className="text-xs bg-blue-600 text-white rounded px-2 py-1 hover:bg-blue-700 disabled:opacity-40"
        >
          {isSaving ? 'Saving...' : 'Save'}
        </button>
      </td>
    </tr>
  );
};

export default TierConfigPage;
