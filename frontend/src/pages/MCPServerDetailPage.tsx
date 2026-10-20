import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
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

const PANEL_TABS: { id: PanelTab; label: string }[] = [
  { id: 'general', label: 'General' },
  { id: 'endpoints', label: 'Endpoints' },
  { id: 'connection', label: 'Conexión' },
];

const CLIENT_TABS: { id: ClientTab; label: string }[] = [
  { id: 'claude', label: 'Claude Desktop' },
  { id: 'cursor', label: 'Cursor' },
  { id: 'curl', label: 'Test with cURL' },
];

const PANEL_CARD_TITLE = 'font-display text-[17px] font-medium text-fg dark:text-fg-dark mb-3';
const PANEL_DT = 'text-sm text-fg-tertiary dark:text-fg-tertiary-dark';
const PANEL_DD = 'text-sm font-medium text-fg dark:text-fg-dark';

function formatDate(value?: string): string {
  return value ? new Date(value).toLocaleString() : 'N/A';
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
  return (
    <div className="space-y-2">
      <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">{label}</p>
      <code className="block break-all text-sm text-fg dark:text-fg-dark">{url}</code>
      <ButtonApp
        label={copied ? 'Copiado' : 'Copiar endpoint'}
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
  const [tab, setTab] = useState<PanelTab>('general');
  const [client, setClient] = useState<ClientTab>('claude');
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const agents = server.agents ?? [];
  const hints = server.connection_hints;

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
              label={server.is_active ? 'Activo' : 'Inactivo'}
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
            label="Editar"
            to={`/apps/${appId}/mcp-servers/${server.server_id}/edit`}
            variant="primary"
            size="medium"
            className="flex-1"
            icon={<Pencil className="h-4 w-4" aria-hidden="true" />}
          />
          {onDelete && (
            <ButtonApp
              label="Eliminar"
              onClick={onDelete}
              variant="danger"
              size="medium"
              icon={<Trash2 className="h-4 w-4" aria-hidden="true" />}
            />
          )}
        </div>
      )}

      <SegmentedTabs
        tabs={PANEL_TABS}
        activeTab={tab}
        onChange={setTab}
        ariaLabel="MCP server details"
      />

      {tab === 'general' && (
        <>
          <CardApp>
            <h4 className={PANEL_CARD_TITLE}>Información del servidor</h4>
            <dl className="space-y-3.5">
              <div>
                <dt className={PANEL_DT}>Slug</dt>
                <dd className={`${PANEL_DD} mt-1`}>/{server.slug}</dd>
              </div>
              <div className="border-t border-line pt-3.5 dark:border-line-dark">
                <dt className={PANEL_DT}>Rate Limit</dt>
                <dd className={`${PANEL_DD} mt-1`}>
                  {server.rate_limit === 0 ? 'Unlimited' : `${server.rate_limit} requests/min`}
                </dd>
              </div>
              <div className="grid grid-cols-2 gap-4 border-t border-line pt-3.5 dark:border-line-dark">
                <div>
                  <dt className={PANEL_DT}>Creado</dt>
                  <dd className={`${PANEL_DD} mt-1`}>{formatDate(server.create_date)}</dd>
                </div>
                <div>
                  <dt className={PANEL_DT}>Actualizado</dt>
                  <dd className={`${PANEL_DD} mt-1`}>{formatDate(server.update_date)}</dd>
                </div>
              </div>
            </dl>
          </CardApp>

          <CardApp>
            <div className="mb-3 flex items-center justify-between gap-2">
              <h4 className="font-display text-[17px] font-medium text-fg dark:text-fg-dark">Agentes expuestos</h4>
              <span className="rounded-full bg-surface-hover px-2 py-0.5 text-xs text-fg-secondary dark:bg-surface-hover-dark dark:text-fg-secondary-dark">
                {agents.length}
              </span>
            </div>
            {agents.some((agent) => !agent.is_available) && (
              <Alert
                type="warning"
                className="mb-3"
                message="Some agents are unavailable and won't be exposed as tools. They may have been deleted or unmarked as tools."
              />
            )}
            {agents.length === 0 ? (
              <p className="text-sm text-fg-tertiary dark:text-fg-tertiary-dark">No agents exposed yet.</p>
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
                        {!agent.is_available && <Badge label="Unavailable" variant="error" />}
                      </p>
                      {agent.agent_description && (
                        <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">{agent.agent_description}</p>
                      )}
                      {!agent.is_available && agent.unavailable_reason && (
                        <p className="mt-0.5 text-xs text-error dark:text-error-dark">Reason: {agent.unavailable_reason}</p>
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
          <h4 className={PANEL_CARD_TITLE}>Endpoint URLs</h4>
          <div className="space-y-5">
            <EndpointBlock
              label="Primary Endpoint (slug-based)"
              url={server.endpoint_url}
              copied={copiedField === 'endpoint'}
              onCopy={() => copy(server.endpoint_url, 'endpoint')}
            />
            {server.endpoint_url_by_id && (
              <EndpointBlock
                label="Fallback Endpoint (ID-based)"
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
          <h4 className={PANEL_CARD_TITLE}>Connection Configuration</h4>
          {hints ? (
            <>
              <p className="mb-2 text-sm text-fg-secondary dark:text-fg-secondary-dark">
                Selecciona el cliente para consultar las instrucciones de conexión.
              </p>
              <Tabs tabs={CLIENT_TABS} activeTab={client} onChange={(id) => setClient(id as ClientTab)} />
              <div className="relative mt-4">
                <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded-lg bg-gray-900 p-4 text-xs text-gray-100">
                  {snippet}
                </pre>
                <button
                  type="button"
                  onClick={() => copy(snippet, client)}
                  className="absolute right-2 top-2 rounded bg-gray-700 px-2 py-1 text-xs text-white hover:bg-gray-600"
                >
                  {copiedField === client ? 'Copiado' : 'Copiar'}
                </button>
              </div>
            </>
          ) : (
            <p className="text-sm text-fg-tertiary dark:text-fg-tertiary-dark">No hay instrucciones de conexión disponibles.</p>
          )}
          <div className="mt-5 space-y-1.5">
            <h5 className="flex items-center gap-2 text-sm font-medium text-fg dark:text-fg-dark">
              <ShieldCheck className="h-4 w-4 text-fg-tertiary dark:text-fg-tertiary-dark" aria-hidden="true" />
              Authentication Required
            </h5>
            <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">
              Los endpoints MCP requieren autenticación mediante API key y la cabecera <code>X-API-KEY</code>.
            </p>
            <Link
              to={`/apps/${appId}/settings/api-keys`}
              className="text-sm text-bronze  dark:text-bronze-dark inline-block"
            >
              Manage API Keys
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
      setError(err instanceof Error ? err.message : 'Failed to load MCP server');
      console.error('Error loading MCP server:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete() {
    if (!confirm('Are you sure you want to delete this MCP server? This action cannot be undone.')) {
      return;
    }

    if (!appId || !serverId) return;

    try {
      await apiService.deleteMCPServer(Number.parseInt(appId), Number.parseInt(serverId));
      navigate(`/apps/${appId}/mcp-servers`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete MCP server');
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
    return <p className="px-4 py-6 text-sm text-fg-tertiary dark:text-fg-tertiary-dark">Loading...</p>;
  }
  if (isPanel && (error || !server)) {
    return <div className="px-4 py-4"><Alert type="error" message={error || 'MCP server not found'} /></div>;
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">MCP Server Details</h1>
            <p className="text-gray-600">Loading...</p>
          </div>
          <Title variant="titPrincipal" titulo="MCP Server Details"></Title>
        </div>

        <LoadingState variant="page" message="Loading MCP server..." />
      </div>
    );
  }

  if (error || !server) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <Title variant="titPrincipal" titulo="MCP Server Details"></Title>
          </div>
        </div>

        <Alert
          type="error"
          message={(
            <>
              {error || 'MCP server not found'}
              <Link to={`/apps/${appId}/mcp-servers`} className="mt-2 block underline">
                Back to MCP Servers
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
          <Title variant="titPrincipal" titulo={server.name} subtitulo={server.description || 'No description'} subtitleMarginBottom={0}></Title>
        <Badge
              label={server.is_active ? 'Active' : 'Inactive'}
              variant={server.is_active ? 'success' : 'default'}
            />
        </div>
        
        <div className="flex space-x-2">
          {canEdit && (
            <>
              <ButtonLink
                label="Edit"
                to={`/apps/${appId}/mcp-servers/${serverId}/edit`}
                variant="primary"
                size="medium"
              />
              <ButtonApp
                label="Delete"
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
          <h2 className="text-[11px] font-semibold text-bronze dark:text-bronze-dark uppercase mb-4">Server Information</h2>
          <dl className="space-y-3">
            <div>
              <dt className="text-sm text-gray-500">Slug</dt>
              <dd className="text-sm font-medium text-gray-900">/{server.slug}</dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">Rate Limit</dt>
              <dd className="text-sm font-medium text-gray-900">
                {server.rate_limit === 0 ? 'Unlimited' : `${server.rate_limit} requests/min`}
              </dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">Created</dt>
              <dd className="text-sm font-medium text-gray-900">
                {server.create_date ? new Date(server.create_date).toLocaleString() : 'N/A'}
              </dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">Last Updated</dt>
              <dd className="text-sm font-medium text-gray-900">
                {server.update_date ? new Date(server.update_date).toLocaleString() : 'N/A'}
              </dd>
            </div>
          </dl>
        </CardApp>

        {/* Agents Card */}
        <CardApp className="p-6">
          <h2 className="text-[11px] font-semibold text-bronze dark:text-bronze-dark uppercase mb-4">Exposed Agents ({server.agents?.length || 0})</h2>

          {/* Warning for unavailable agents */}
          {server.agents && server.agents.some(a => !a.is_available) && (
            <Alert
              type="warning"
              className="mb-4"
              message="Some agents are unavailable and won't be exposed as tools. They may have been deleted or unmarked as tools."
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
                          Unavailable
                        </span>
                      )}
                    </div>
                    {agent.agent_description && (
                      <div className="text-xs text-gray-500">{agent.agent_description}</div>
                    )}
                    {!agent.is_available && agent.unavailable_reason && (
                      <div className="text-xs text-red-600 mt-1">
                        Reason: {agent.unavailable_reason}
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-gray-500">No agents exposed yet.</p>
          )}
        </CardApp>
      </div>

      {/* Endpoint URLs */}
      <CardApp className="p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Endpoint URLs</h2>

        <div className="space-y-4">
          <div>
            <p className="block text-sm font-medium text-gray-700 mb-1">
              Primary Endpoint (slug-based)
            </p>
            <div className="flex items-center space-x-2">
              <code className="flex-1 p-3 bg-gray-100 rounded-lg text-sm font-mono break-all">
                {server.endpoint_url}
              </code>
              <button
                onClick={() => copyToClipboard(server.endpoint_url, 'endpoint')}
                className="px-3 py-2 text-sm bg-gray-200 hover:bg-gray-300 rounded-lg"
              >
                {copiedField === 'endpoint' ? 'Copied!' : 'Copy'}
              </button>
            </div>
          </div>

          {server.endpoint_url_by_id && (
            <div>
              <p className="block text-sm font-medium text-gray-700 mb-1">
                Fallback Endpoint (ID-based)
              </p>
              <div className="flex items-center space-x-2">
                <code className="flex-1 p-3 bg-gray-100 rounded-lg text-sm font-mono break-all">
                  {server.endpoint_url_by_id}
                </code>
                <button
                  onClick={() => copyToClipboard(server.endpoint_url_by_id!, 'endpoint_id')}
                  className="px-3 py-2 text-sm bg-gray-200 hover:bg-gray-300 rounded-lg"
                >
                  {copiedField === 'endpoint_id' ? 'Copied!' : 'Copy'}
                </button>
              </div>
            </div>
          )}
        </div>
      </CardApp>

      {/* Connection Hints */}
      {server.connection_hints && (
        <CardApp className="p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Connection Configuration</h2>

          {/* Claude Desktop */}
          <div className="mb-6">
            <h3 className="text-md font-medium text-gray-800 mb-2">Claude Desktop</h3>
            <p className="text-sm text-gray-600 mb-2">
              Add this configuration to your Claude Desktop settings file
              (<code className="text-xs bg-gray-100 px-1 rounded">claude_desktop_config.json</code>):
            </p>
            <div className="relative">
              <pre className="p-4 bg-gray-900 text-green-400 rounded-lg text-sm overflow-x-auto">
                {JSON.stringify(server.connection_hints.claude_desktop, null, 2)}
              </pre>
              <button
                onClick={() => copyToClipboard(JSON.stringify(server.connection_hints!.claude_desktop, null, 2), 'claude')}
                className="absolute top-2 right-2 px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-white rounded"
              >
                {copiedField === 'claude' ? 'Copied!' : 'Copy'}
              </button>
            </div>
          </div>

          {/* Cursor */}
          <div className="mb-6">
            <h3 className="text-md font-medium text-gray-800 mb-2">Cursor</h3>
            <p className="text-sm text-gray-600 mb-2">
              Add this to your Cursor MCP settings:
            </p>
            <div className="relative">
              <pre className="p-4 bg-gray-900 text-green-400 rounded-lg text-sm overflow-x-auto">
                {JSON.stringify(server.connection_hints.cursor, null, 2)}
              </pre>
              <button
                onClick={() => copyToClipboard(JSON.stringify(server.connection_hints!.cursor, null, 2), 'cursor')}
                className="absolute top-2 right-2 px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-white rounded"
              >
                {copiedField === 'cursor' ? 'Copied!' : 'Copy'}
              </button>
            </div>
          </div>

          {/* Curl Example */}
          <div>
            <h3 className="text-md font-medium text-gray-800 mb-2">Test with curl</h3>
            <p className="text-sm text-gray-600 mb-2">
              Test the MCP endpoint using curl:
            </p>
            <div className="relative">
              <pre className="p-4 bg-gray-900 text-green-400 rounded-lg text-sm overflow-x-auto whitespace-pre-wrap">
                {server.connection_hints.curl_example}
              </pre>
              <button
                onClick={() => copyToClipboard(server.connection_hints!.curl_example, 'curl')}
                className="absolute top-2 right-2 px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-white rounded"
              >
                {copiedField === 'curl' ? 'Copied!' : 'Copy'}
              </button>
            </div>
          </div>
        </CardApp>
      )}

      {/* Authentication Note */}
      <Alert
        type="info"
        title="Authentication Required"
        message={(
          <>
            MCP endpoints require authentication. Use an API key from your app's API Keys settings
            and include it in the <code>X-API-KEY</code> header.
            <Link to={`/apps/${appId}/settings/api-keys`} className="mt-2 block underline">
              Manage API Keys
            </Link>
          </>
        )}
      />
    </div>
  );
}

export default MCPServerDetailPage;
