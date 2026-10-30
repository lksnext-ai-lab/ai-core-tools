import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowUpRight, Bot, Copy, Pencil, ShieldCheck, Trash2 } from 'lucide-react';
import { apiService } from '../services/api';
import { useAppRole } from '../hooks/useAppRole';
import { AppRole } from '../types/roles';
import type { MCPConnectionHints, MCPServer } from '../core/types';
import { LoadingState } from '../components/ui/LoadingState';
import { ButtonApp } from '../components/ui/ButtonApp';
import ButtonLink from '../components/ui/ButtonLink';
import Badge from '../components/ui/Badge';
import Alert from '../components/ui/Alert';
import Title from '../components/ui/Title';
import CardApp from '../components/ui/CardApp';
import { Tabs } from '../components/ui/Tabs';
import { SegmentedTabs } from '../components/ui/SegmentedTabs';

type PanelTab = 'general' | 'endpoints' | 'connection';
type ClientTab = 'claude' | 'cursor' | 'curl';

const PANEL_CARD_TITLE = 'font-display text-[17px] font-medium text-fg dark:text-fg-dark mb-3';
const PANEL_DT = 'text-sm text-fg-tertiary dark:text-fg-tertiary-dark';
const PANEL_DD = 'text-sm font-medium text-fg dark:text-fg-dark';

function formatDate(value: string | undefined, locale: string | undefined, notAvailable: string): string {
  return value ? new Date(value).toLocaleString(locale) : notAvailable;
}

function clientSnippet(hints: MCPConnectionHints, client: ClientTab): string {
  if (client === 'claude') return JSON.stringify(hints.claude_desktop, null, 2);
  if (client === 'cursor') return JSON.stringify(hints.cursor, null, 2);
  return hints.curl_example;
}

interface EndpointBlockProps {
  readonly label: string;
  readonly url: string;
  readonly copied: boolean;
  readonly onCopy: () => void;
}

function EndpointBlock({ label, url, copied, onCopy }: Readonly<EndpointBlockProps>) {
  const { t } = useTranslation('common');

  return (
    <div className="space-y-2">
      <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">{label}</p>
      <code className="block break-all text-sm text-fg dark:text-fg-dark">{url}</code>
      <ButtonApp
        label={t(copied ? 'mcpServerDetailPage.actions.copied' : 'mcpServerDetailPage.actions.copyEndpoint')}
        onClick={onCopy}
        variant="muted"
        size="small"
        className="w-full !rounded-full"
        icon={<Copy className="h-3.5 w-3.5" aria-hidden="true" />}
      />
    </div>
  );
}

interface PanelViewProps {
  readonly server: MCPServer;
  readonly appId: string | undefined;
  readonly canEdit: boolean;
  readonly onDelete?: () => void;
}

/** Compact single-column MCP server detail shown in the MCP servers side panel. */
function MCPServerPanelView({ server, appId, canEdit, onDelete }: Readonly<PanelViewProps>) {
  const { t, i18n } = useTranslation('common');
  const [tab, setTab] = useState<PanelTab>('general');
  const [client, setClient] = useState<ClientTab>('claude');
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const agents = server.agents ?? [];
  const hints = server.connection_hints;
  const panelTabs: { id: PanelTab; label: string }[] = [
    { id: 'general', label: t('mcpServerDetailPage.tabs.general') },
    { id: 'endpoints', label: t('mcpServerDetailPage.tabs.endpoints') },
    { id: 'connection', label: t('mcpServerDetailPage.tabs.connection') },
  ];
  const clientTabs: { id: ClientTab; label: string }[] = [
    { id: 'claude', label: 'Claude Desktop' },
    { id: 'cursor', label: 'Cursor' },
    { id: 'curl', label: t('mcpServerDetailPage.tabs.testCurl') },
  ];

  function copy(text: string, field: string) {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedField(field);
      setTimeout(() => setCopiedField(null), 2000);
    }).catch(() => {
      // nothing was copied, so no confirmation is shown
    });
  }

  const snippet = hints ? clientSnippet(hints, client) : '';

  return (
    <div className="space-y-4 px-4 py-4">
      <div className="min-w-0">
        <div className="flex items-center justify-between gap-3">
          <h3 className="min-w-0 font-display text-[22px] leading-tight text-fg dark:text-fg-dark break-words">{server.name}</h3>
          <span className="flex-shrink-0">
            <Badge
              label={t(server.is_active ? 'mcpServersPage.statuses.active' : 'mcpServersPage.statuses.inactive')}
              variant={server.is_active ? 'success' : 'default'}
            />
          </span>
        </div>
        {server.description && (
          <p className="mt-1 text-sm text-fg-tertiary dark:text-fg-tertiary-dark break-words">{server.description}</p>
        )}
      </div>

      {canEdit && (
        <div className="flex gap-2">
          <ButtonLink
            label={t('mcpServerDetailPage.actions.edit')}
            to={`/apps/${appId}/mcp-servers/${server.server_id}/edit`}
            variant="primary"
            size="medium"
            className="flex-1"
            icon={<Pencil className="h-4 w-4" aria-hidden="true" />}
          />
          {onDelete && (
            <ButtonApp
              label={t('mcpServerDetailPage.actions.delete')}
              onClick={onDelete}
              variant="danger"
              size="medium"
              icon={<Trash2 className="h-4 w-4" aria-hidden="true" />}
            />
          )}
        </div>
      )}

      <SegmentedTabs
        tabs={panelTabs}
        activeTab={tab}
        onChange={setTab}
        ariaLabel={t('mcpServerDetailPage.aria.detailsTabs')}
      />

      {tab === 'general' && (
        <>
          <CardApp>
            <h4 className={PANEL_CARD_TITLE}>{t('mcpServerDetailPage.sections.serverInformation')}</h4>
            <dl className="space-y-3.5">
              <div>
                <dt className={PANEL_DT}>{t('mcpServerDetailPage.fields.slug')}</dt>
                <dd className={`${PANEL_DD} mt-1`}>/{server.slug}</dd>
              </div>
              <div className="border-t border-line pt-3.5 dark:border-line-dark">
                <dt className={PANEL_DT}>{t('mcpServerDetailPage.fields.rateLimit')}</dt>
                <dd className={`${PANEL_DD} mt-1`}>
                  {server.rate_limit === 0
                    ? t('mcpServerDetailPage.unlimited')
                    : t('mcpServerDetailPage.requestsPerMinute', { count: server.rate_limit })}
                </dd>
              </div>
              <div className="grid grid-cols-2 gap-4 border-t border-line pt-3.5 dark:border-line-dark">
                <div>
                  <dt className={PANEL_DT}>{t('mcpServerDetailPage.fields.created')}</dt>
                  <dd className={`${PANEL_DD} mt-1`}>{formatDate(server.create_date, i18n.resolvedLanguage, t('mcpServerDetailPage.notAvailable'))}</dd>
                </div>
                <div>
                  <dt className={PANEL_DT}>{t('mcpServerDetailPage.fields.updated')}</dt>
                  <dd className={`${PANEL_DD} mt-1`}>{formatDate(server.update_date, i18n.resolvedLanguage, t('mcpServerDetailPage.notAvailable'))}</dd>
                </div>
              </div>
            </dl>
          </CardApp>

          <CardApp>
            <div className="mb-3 flex items-center justify-between gap-2">
              <h4 className="font-display text-[17px] font-medium text-fg dark:text-fg-dark">{t('mcpServerDetailPage.sections.exposedAgents')}</h4>
              <span className="rounded-full bg-surface-hover px-2 py-0.5 text-xs text-fg-secondary dark:bg-surface-hover-dark dark:text-fg-secondary-dark">
                {agents.length}
              </span>
            </div>
            {agents.some((agent) => !agent.is_available) && (
              <Alert
                type="warning"
                className="mb-3"
                message={t('mcpServerDetailPage.messages.unavailableAgents')}
              />
            )}
            {agents.length === 0 ? (
              <p className="text-sm text-fg-tertiary dark:text-fg-tertiary-dark">{t('mcpServerDetailPage.messages.noAgents')}</p>
            ) : (
              <ul className="space-y-3">
                {agents.map((agent) => (
                  <li key={agent.agent_id} className="flex items-start gap-2.5">
                    <Bot
                      className={`mt-0.5 h-4 w-4 flex-shrink-0 ${agent.is_available ? 'text-fg-tertiary dark:text-fg-tertiary-dark' : 'text-error dark:text-error-dark'}`}
                      aria-hidden="true"
                    />
                    <div className="min-w-0">
                      <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-fg dark:text-fg-dark">
                        {agent.tool_name_override || agent.agent_name}
                        {!agent.is_available && <Badge label={t('mcpServerDetailPage.statuses.unavailable')} variant="error" />}
                      </p>
                      {agent.agent_description && (
                        <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">{agent.agent_description}</p>
                      )}
                      {!agent.is_available && agent.unavailable_reason && (
                        <p className="mt-0.5 text-xs text-error dark:text-error-dark">{t('mcpServerDetailPage.fields.reason', { reason: agent.unavailable_reason })}</p>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardApp>
        </>
      )}

      {tab === 'endpoints' && (
        <CardApp>
          <h4 className={PANEL_CARD_TITLE}>{t('mcpServerDetailPage.sections.endpointUrls')}</h4>
          <div className="space-y-5">
            <EndpointBlock
              label={t('mcpServerDetailPage.fields.primaryEndpoint')}
              url={server.endpoint_url}
              copied={copiedField === 'endpoint'}
              onCopy={() => copy(server.endpoint_url, 'endpoint')}
            />
            {server.endpoint_url_by_id && (
              <EndpointBlock
                label={t('mcpServerDetailPage.fields.fallbackEndpoint')}
                url={server.endpoint_url_by_id}
                copied={copiedField === 'endpoint_id'}
                onCopy={() => copy(server.endpoint_url_by_id!, 'endpoint_id')}
              />
            )}
          </div>
        </CardApp>
      )}

      {tab === 'connection' && (
        <CardApp>
          <h4 className={PANEL_CARD_TITLE}>{t('mcpServerDetailPage.sections.connectionConfiguration')}</h4>
          {hints ? (
            <>
              <p className="mb-2 text-sm text-fg-secondary dark:text-fg-secondary-dark">
                {t('mcpServerDetailPage.messages.selectClient')}
              </p>
              <Tabs tabs={clientTabs} activeTab={client} onChange={(id) => setClient(id as ClientTab)} />
              <div className="relative mt-4">
                <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded-lg bg-gray-900 p-4 text-xs text-gray-100">
                  {snippet}
                </pre>
                <ButtonApp
                  label={t(copiedField === client ? 'mcpServerDetailPage.actions.copied' : 'mcpServerDetailPage.actions.copy')}
                  onClick={() => copy(snippet, client)}
                  variant="secondary"
                  size="medium"
                  className="absolute right-2 top-2"
                />
              </div>
            </>
          ) : (
            <p className="text-sm text-fg-tertiary dark:text-fg-tertiary-dark">{t('mcpServerDetailPage.messages.noConnectionInstructions')}</p>
          )}
          <div className="mt-5 space-y-1.5">
            <h5 className="flex items-center gap-2 text-sm font-medium text-fg dark:text-fg-dark">
              <ShieldCheck className="h-4 w-4 text-fg-tertiary dark:text-fg-tertiary-dark" aria-hidden="true" />
              {t('mcpServerDetailPage.sections.authenticationRequired')}
            </h5>
            <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">
              {t('mcpServerDetailPage.messages.apiKeyRequired')} <code>X-API-KEY</code>.
            </p>
            <Link
              to={`/apps/${appId}/settings/api-keys`}
              className="text-sm text-bronze  dark:text-bronze-dark inline-block"
            >
              {t('mcpServerDetailPage.actions.manageApiKeys')}
              <ArrowUpRight className="w-4 h-4 inline-block ml-1" aria-hidden="true" />

            </Link>
          </div>
        </CardApp>
      )}
    </div>
  );
}

interface DetailPageProps {
  /** Overrides the `:serverId` route param when embedded in the side panel. */
  readonly serverId?: number;
  readonly variant?: 'page' | 'panel';
  /** Panel only: delete is handled by the parent so it can close the panel and refresh its list. */
  readonly onDelete?: () => void;
}

function MCPServerDetailPage({ serverId: serverIdProp, variant = 'page', onDelete }: Readonly<DetailPageProps>) {
  const { appId, serverId: serverIdParam } = useParams();
  const { t, i18n } = useTranslation('common');
  const serverId = serverIdProp === undefined ? serverIdParam : String(serverIdProp);
  const isPanel = variant === 'panel';
  const navigate = useNavigate();
  const { hasMinRole } = useAppRole(appId);
  const canEdit = hasMinRole(AppRole.ADMINISTRATOR);

  const [server, setServer] = useState<MCPServer | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedField, setCopiedField] = useState<string | null>(null);

  useEffect(() => {
    if (!appId || !serverId) return;
    void loadServer();
  }, [appId, serverId]);

  async function loadServer() {
    if (!appId || !serverId) return;

    try {
      setLoading(true);
      setError(null);
      const response = await apiService.getMCPServer(Number.parseInt(appId), Number.parseInt(serverId));
      setServer(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('mcpServerDetailPage.errors.loadFailed'));
      console.error('Error loading MCP server:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete() {
    if (!confirm(t('mcpServerDetailPage.confirmDelete'))) {
      return;
    }

    if (!appId || !serverId) return;

    try {
      await apiService.deleteMCPServer(Number.parseInt(appId), Number.parseInt(serverId));
      navigate(`/apps/${appId}/mcp-servers`);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('mcpServerDetailPage.errors.deleteFailed'));
    }
  }

  function copyToClipboard(text: string, field: string) {
    // Only show "copied" once the clipboard write actually succeeded (it can be
    // rejected, e.g. without clipboard permission or when the page lacks focus).
    navigator.clipboard.writeText(text).then(() => {
      setCopiedField(field);
      setTimeout(() => setCopiedField(null), 2000);
    }).catch(() => {
      // ignore: nothing was copied, so no confirmation is shown
    });
  }

  if (isPanel && loading) {
    return <p className="px-4 py-6 text-sm text-fg-tertiary dark:text-fg-tertiary-dark">{t('mcpServerDetailPage.loading')}</p>;
  }
  if (isPanel && (error || !server)) {
    return <div className="px-4 py-4"><Alert type="error" message={error || t('mcpServerDetailPage.notFound')} /></div>;
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{t('mcpServerDetailPage.title')}</h1>
            <p className="text-gray-600">{t('mcpServerDetailPage.loading')}</p>
          </div>
          <Title variant="titPrincipal" titulo={t('mcpServerDetailPage.title')}></Title>
        </div>

        <LoadingState variant="page" message={t('mcpServerDetailPage.loadingServer')} />
      </div>
    );
  }

  if (error || !server) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <Title variant="titPrincipal" titulo={t('mcpServerDetailPage.title')}></Title>
          </div>
        </div>

        <Alert
          type="error"
          message={(
            <>
              {error || t('mcpServerDetailPage.notFound')}
              <Link to={`/apps/${appId}/mcp-servers`} className="mt-2 block underline">
                {t('mcpServerDetailPage.actions.backToServers')}
              </Link>
            </>
          )}
        />
      </div>
    );
  }

  if (isPanel) {
    return <MCPServerPanelView server={server} appId={appId} canEdit={canEdit} onDelete={onDelete} />;
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <Title variant="titPrincipal" titulo={server.name} subtitulo={server.description || t('mcpServerDetailPage.noDescription')} subtitleMarginBottom={0}></Title>
        <Badge
              label={t(server.is_active ? 'mcpServersPage.statuses.active' : 'mcpServersPage.statuses.inactive')}
              variant={server.is_active ? 'success' : 'default'}
            />
        </div>
        
        <div className="flex space-x-2">
          {canEdit && (
            <>
              <ButtonLink
                label={t('mcpServerDetailPage.actions.edit')}
                to={`/apps/${appId}/mcp-servers/${serverId}/edit`}
                variant="primary"
                size="medium"
              />
              <ButtonApp
                label={t('mcpServerDetailPage.actions.delete')}
                onClick={handleDelete}
                variant="danger"
                size="medium"
              />
            </>
          )}
        </div>
      </div>

      {/* Server Info */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Basic Info Card */}
        <CardApp className="p-6">
          <h2 className="text-[11px] font-semibold text-bronze dark:text-bronze-dark uppercase mb-4">{t('mcpServerDetailPage.sections.serverInformation')}</h2>
          <dl className="space-y-3">
            <div>
              <dt className="text-sm text-gray-500">{t('mcpServerDetailPage.fields.slug')}</dt>
              <dd className="text-sm font-medium text-gray-900">/{server.slug}</dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">{t('mcpServerDetailPage.fields.rateLimit')}</dt>
              <dd className="text-sm font-medium text-gray-900">
                {server.rate_limit === 0
                  ? t('mcpServerDetailPage.unlimited')
                  : t('mcpServerDetailPage.requestsPerMinute', { count: server.rate_limit })}
              </dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">{t('mcpServerDetailPage.fields.created')}</dt>
              <dd className="text-sm font-medium text-gray-900">
                {formatDate(server.create_date, i18n.resolvedLanguage, t('mcpServerDetailPage.notAvailable'))}
              </dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">{t('mcpServerDetailPage.fields.updated')}</dt>
              <dd className="text-sm font-medium text-gray-900">
                {formatDate(server.update_date, i18n.resolvedLanguage, t('mcpServerDetailPage.notAvailable'))}
              </dd>
            </div>
          </dl>
        </CardApp>

        {/* Agents Card */}
        <CardApp className="p-6">
          <h2 className="text-[11px] font-semibold text-bronze dark:text-bronze-dark uppercase mb-4">{t('mcpServerDetailPage.sections.exposedAgentsCount', { count: server.agents?.length || 0 })}</h2>

          {/* Warning for unavailable agents */}
          {server.agents && server.agents.some(a => !a.is_available) && (
            <Alert
              type="warning"
              className="mb-4"
              message={t('mcpServerDetailPage.messages.unavailableAgents')}
            />
          )}

          {server.agents && server.agents.length > 0 ? (
            <ul className="space-y-2">
              {server.agents.map(agent => (
                <li
                  key={agent.agent_id}
                  className={`flex items-start p-2 rounded ${
                    agent.is_available ? 'bg-gray-50' : 'bg-red-50 border border-red-200'
                  }`}
                >
                  <span className={`mr-2 ${agent.is_available ? 'text-purple-500' : 'text-red-400'}`}>
                    {agent.is_available ? 'o' : '!'}
                  </span>
                  <div className="flex-1">
                    <div className={`text-sm font-medium ${agent.is_available ? 'text-gray-900' : 'text-red-700'}`}>
                      {agent.tool_name_override || agent.agent_name}
                      {!agent.is_available && (
                        <span className="ml-2 px-2 py-0.5 text-xs bg-red-100 text-red-700 rounded-full">
                          {t('mcpServerDetailPage.statuses.unavailable')}
                        </span>
                      )}
                    </div>
                    {agent.agent_description && (
                      <div className="text-xs text-gray-500">{agent.agent_description}</div>
                    )}
                    {!agent.is_available && agent.unavailable_reason && (
                      <div className="text-xs text-red-600 mt-1">
                        {t('mcpServerDetailPage.fields.reason', { reason: agent.unavailable_reason })}
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-gray-500">{t('mcpServerDetailPage.messages.noAgents')}</p>
          )}
        </CardApp>
      </div>

      {/* Endpoint URLs */}
      <CardApp className="p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">{t('mcpServerDetailPage.sections.endpointUrls')}</h2>

        <div className="space-y-4">
          <div>
            <p className="block text-sm font-medium text-gray-700 mb-1">
              {t('mcpServerDetailPage.fields.primaryEndpoint')}
            </p>
            <div className="flex items-center space-x-2">
              <code className="flex-1 p-3 bg-gray-100 rounded-lg text-sm font-mono break-all">
                {server.endpoint_url}
              </code>
              <button
                onClick={() => copyToClipboard(server.endpoint_url, 'endpoint')}
                className="px-3 py-2 text-sm bg-gray-200 hover:bg-gray-300 rounded-lg"
              >
                {t(copiedField === 'endpoint' ? 'mcpServerDetailPage.actions.copied' : 'mcpServerDetailPage.actions.copy')}
              </button>
            </div>
          </div>

          {server.endpoint_url_by_id && (
            <div>
              <p className="block text-sm font-medium text-gray-700 mb-1">
                {t('mcpServerDetailPage.fields.fallbackEndpoint')}
              </p>
              <div className="flex items-center space-x-2">
                <code className="flex-1 p-3 bg-gray-100 rounded-lg text-sm font-mono break-all">
                  {server.endpoint_url_by_id}
                </code>
                <button
                  onClick={() => copyToClipboard(server.endpoint_url_by_id!, 'endpoint_id')}
                  className="px-3 py-2 text-sm bg-gray-200 hover:bg-gray-300 rounded-lg"
                >
                  {t(copiedField === 'endpoint_id' ? 'mcpServerDetailPage.actions.copied' : 'mcpServerDetailPage.actions.copy')}
                </button>
              </div>
            </div>
          )}
        </div>
      </CardApp>

      {/* Connection Hints */}
      {server.connection_hints && (
        <CardApp className="p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">{t('mcpServerDetailPage.sections.connectionConfiguration')}</h2>

          {/* Claude Desktop */}
          <div className="mb-6">
            <h3 className="text-md font-medium text-gray-800 mb-2">Claude Desktop</h3>
            <p className="text-sm text-gray-600 mb-2">
              {t('mcpServerDetailPage.messages.claudeConfig')} (<code className="text-xs bg-gray-100 px-1 rounded">claude_desktop_config.json</code>):
            </p>
            <div className="relative">
              <pre className="p-4 bg-gray-900 text-green-400 rounded-lg text-sm overflow-x-auto">
                {JSON.stringify(server.connection_hints.claude_desktop, null, 2)}
              </pre>
              <button
                onClick={() => copyToClipboard(JSON.stringify(server.connection_hints!.claude_desktop, null, 2), 'claude')}
                className="absolute top-2 right-2 px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-white rounded"
              >
                {t(copiedField === 'claude' ? 'mcpServerDetailPage.actions.copied' : 'mcpServerDetailPage.actions.copy')}
              </button>
            </div>
          </div>

          {/* Cursor */}
          <div className="mb-6">
            <h3 className="text-md font-medium text-gray-800 mb-2">Cursor</h3>
            <p className="text-sm text-gray-600 mb-2">
              {t('mcpServerDetailPage.messages.cursorConfig')}
            </p>
            <div className="relative">
              <pre className="p-4 bg-gray-900 text-green-400 rounded-lg text-sm overflow-x-auto">
                {JSON.stringify(server.connection_hints.cursor, null, 2)}
              </pre>
              <button
                onClick={() => copyToClipboard(JSON.stringify(server.connection_hints!.cursor, null, 2), 'cursor')}
                className="absolute top-2 right-2 px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-white rounded"
              >
                {t(copiedField === 'cursor' ? 'mcpServerDetailPage.actions.copied' : 'mcpServerDetailPage.actions.copy')}
              </button>
            </div>
          </div>

          {/* Curl Example */}
          <div>
            <h3 className="text-md font-medium text-gray-800 mb-2">{t('mcpServerDetailPage.tabs.testCurl')}</h3>
            <p className="text-sm text-gray-600 mb-2">
              {t('mcpServerDetailPage.messages.curlConfig')}
            </p>
            <div className="relative">
              <pre className="p-4 bg-gray-900 text-green-400 rounded-lg text-sm overflow-x-auto whitespace-pre-wrap">
                {server.connection_hints.curl_example}
              </pre>
              <button
                onClick={() => copyToClipboard(server.connection_hints!.curl_example, 'curl')}
                className="absolute top-2 right-2 px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-white rounded"
              >
                {t(copiedField === 'curl' ? 'mcpServerDetailPage.actions.copied' : 'mcpServerDetailPage.actions.copy')}
              </button>
            </div>
          </div>
        </CardApp>
      )}

      {/* Authentication Note */}
      <Alert
        type="info"
        title={t('mcpServerDetailPage.sections.authenticationRequired')}
        message={(
          <>
            {t('mcpServerDetailPage.messages.apiKeyRequired')} <code>X-API-KEY</code>.
            <Link to={`/apps/${appId}/settings/api-keys`} className="mt-2 block underline">
              {t('mcpServerDetailPage.actions.manageApiKeys')}
            </Link>
          </>
        )}
      />
    </div>
  );
}

export default MCPServerDetailPage;
