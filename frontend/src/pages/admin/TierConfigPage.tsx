import React, { useEffect, useState } from 'react';
import { apiService } from '../../services/api';
import { LoadingState } from '../../components/ui/LoadingState';
import { ErrorState } from '../../components/ui/ErrorState';
import { useApiMutation } from '../../hooks/useApiMutation';
import { errorMessage } from '../../constants/messages';

interface TierConfigEntry {
  readonly id: number;
  readonly tier: string;
  readonly resource_type: string;
  readonly limit_value: number;
}

const TierConfigPage: React.FC = () => {
  const mutate = useApiMutation();
  const [configs, setConfigs] = useState<TierConfigEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    const fetch = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const data = (await apiService.getTierConfig()) as TierConfigEntry[];
        if (isMounted) setConfigs(data);
      } catch (err) {
        if (isMounted) setError(errorMessage(err, 'Failed to load tier config'));
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };
    fetch();
    return () => {
      isMounted = false;
    };
  }, []);

  const handleSave = async (entry: TierConfigEntry, newValue: number) => {
    const key = `${entry.tier}_${entry.resource_type}`;
    setSavingKey(key);
    const result = await mutate(
      () =>
        apiService.updateTierConfig({
          tier: entry.tier,
          resource_type: entry.resource_type,
          limit_value: newValue,
        }),
      {
        loading: 'Saving limit…',
        success: 'Limit updated',
        error: (err) => errorMessage(err, 'Failed to save limit'),
      },
    );
    setSavingKey(null);
    if (result === undefined) return;

    setConfigs((prev) =>
      prev.map((c) => (c.id === entry.id ? { ...c, limit_value: newValue } : c)),
    );
  };

  if (isLoading) return <LoadingState message="Loading tier config..." />;
  if (error) return <ErrorState error={error} onRetry={() => globalThis.location.reload()} />;

  const tiers = [...new Set(configs.map((c) => c.tier))].sort((a, b) => a.localeCompare(b));

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Tier Configuration</h1>
        <p className="text-gray-600">
          Configure resource limits per subscription tier. Use{' '}
          <span className="font-mono">-1</span> to indicate unlimited.
        </p>
      </div>

      {tiers.map((tier) => (
        <section key={tier}>
          <h2 className="text-lg font-semibold text-gray-900 capitalize mb-3">{tier}</h2>
          <div className="bg-white border rounded-lg overflow-x-auto shadow-sm">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Resource
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Limit
                  </th>
                  <th className="px-6 py-3" />
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {configs
                  .filter((c) => c.tier === tier)
                  .map((entry) => (
                    <TierConfigRow
                      key={entry.id}
                      entry={entry}
                      isSaving={savingKey === `${entry.tier}_${entry.resource_type}`}
                      onSave={handleSave}
                    />
                  ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </div>
  );
};

interface TierConfigRowProps {
  readonly entry: TierConfigEntry;
  readonly isSaving: boolean;
  readonly onSave: (entry: TierConfigEntry, value: number) => Promise<void>;
}

const TierConfigRow: React.FC<TierConfigRowProps> = ({ entry, isSaving, onSave }) => {
  const [value, setValue] = useState(entry.limit_value);

  // Sync input value when parent state changes after save
  useEffect(() => {
    setValue(entry.limit_value);
  }, [entry.limit_value]);

  return (
    <tr className="hover:bg-gray-50">
      <td className="px-6 py-3 text-sm text-gray-700">
        {entry.resource_type.replaceAll('_', ' ')}
      </td>
      <td className="px-6 py-3 text-right">
        <input
          type="number"
          value={value}
          onChange={(e) => setValue(Number(e.target.value))}
          className="w-24 border border-gray-300 rounded-md px-2 py-1 text-right text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
      </td>
      <td className="px-6 py-3 text-right">
        <button
          type="button"
          onClick={() => onSave(entry, value)}
          disabled={isSaving || value === entry.limit_value}
          className="text-xs font-medium bg-blue-600 text-white rounded px-3 py-1.5 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {isSaving ? 'Saving…' : 'Save'}
        </button>
      </td>
    </tr>
  );
};

export default TierConfigPage;
