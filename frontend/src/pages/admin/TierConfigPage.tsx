import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiService } from '../../services/api';
import { LoadingState } from '../../components/ui/LoadingState';
import { ErrorState } from '../../components/ui/ErrorState';
import { FormField } from '../../components/ui/FormField';
import { ButtonApp } from '../../components/ui/ButtonApp';
import Table, { type TableColumn } from '../../components/ui/Table';
import { useApiMutation } from '../../hooks/useApiMutation';
import { errorMessage } from '../../constants/messages';
import { Title } from '../../components/ui/Title';

interface TierConfigEntry {
  readonly id: number;
  readonly tier: string;
  readonly resource_type: string;
  readonly limit_value: number;
}

const TierConfigPage: React.FC = () => {
  const { t } = useTranslation('common');
  const mutate = useApiMutation();
  const [configs, setConfigs] = useState<TierConfigEntry[]>([]);
  const [draftValues, setDraftValues] = useState<Record<number, number>>({});
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
        if (isMounted) setError(errorMessage(err, t('tierConfigPage.loadFailed')));
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };
    void fetch();
    return () => {
      isMounted = false;
    };
  }, [t]);

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
        loading: t('tierConfigPage.notifications.savingLimit'),
        success: t('tierConfigPage.notifications.limitUpdated'),
        error: (err) => errorMessage(err, t('tierConfigPage.notifications.saveFailed')),
      },
    );
    setSavingKey(null);
    if (result === undefined) return;

    setConfigs((prev) =>
      prev.map((c) => (c.id === entry.id ? { ...c, limit_value: newValue } : c)),
    );
    setDraftValues((prev) => {
      const next = { ...prev };
      delete next[entry.id];
      return next;
    });
  };

  if (isLoading) return <LoadingState message={t('tierConfigPage.loading')} />;
  if (error) return <ErrorState error={error} onRetry={() => globalThis.location.reload()} />;

  const tiers = [...new Set(configs.map((c) => c.tier))].sort((a, b) => a.localeCompare(b));
  const columns: TableColumn<TierConfigEntry>[] = [
    {
      header: t('tierConfigPage.columns.resource'),
      render: (entry) => entry.resource_type.replaceAll('_', ' '),
      className: 'px-6 py-4 whitespace-nowrap text-sm font-medium text-fg dark:text-fg-dark',
    },
    {
      header: t('tierConfigPage.columns.limit'),
      headerClassName: 'text-right',
      className: 'px-6 py-4 text-right',
      render: (entry) => (
        <FormField
          id={`tier-limit-${entry.id}`}
          label={t('tierConfigPage.actions.limitForResource', {
            resource: entry.resource_type.replaceAll('_', ' '),
            tier: entry.tier,
          })}
          labelClassName="sr-only"
          type="number"
          className="ml-auto w-24"
          inputClassName="text-right"
          value={draftValues[entry.id] ?? entry.limit_value}
          onChange={(event) =>
            setDraftValues((prev) => ({
              ...prev,
              [entry.id]: Number(event.target.value),
            }))
          }
        />
      ),
    },
    {
      header: t('tierConfigPage.columns.actions'),
      sticky: 'right',
      headerClassName: 'text-right',
      className: 'px-6 py-4 whitespace-nowrap text-right',
      render: (entry) => {
        const value = draftValues[entry.id] ?? entry.limit_value;
        const isSaving = savingKey === `${entry.tier}_${entry.resource_type}`;
        return (
          <div className="flex justify-end">
            <ButtonApp
              label={t(isSaving ? 'tierConfigPage.actions.saving' : 'tierConfigPage.actions.save')}
              onClick={() => void handleSave(entry, value)}
              disabled={value === entry.limit_value}
              loading={isSaving}
              variant="primary"
              size="small"
            />
          </div>
        );
      },
    },
  ];

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <Title
        titulo={t('tierConfigPage.title')}
        subtitulo={t('tierConfigPage.subtitle')}
      />

      {tiers.map((tier) => (
        <section key={tier}>
          <Title variant='titTerciario' titulo={tier} />
          <Table
            columns={columns}
            data={configs.filter((entry) => entry.tier === tier)}
            keyExtractor={(entry) => entry.id}
            stickyEdgeColumns
          />
        </section>
      ))}
    </div>
  );
};

export default TierConfigPage;
