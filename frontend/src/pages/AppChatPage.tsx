import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { MessageSquare } from 'lucide-react';

import { apiService } from '../services/api';
import ChatInterface from '../components/playground/ChatInterface';
import ConversationSidebar, { CONVERSATION_PANEL_ID } from '../components/playground/ConversationSidebar';
import { createAppChatTransport, type ChatTransportErrorCode, type ChatTurnEvent } from '../components/playground/chatTransport';
import { ChatSelectionBar } from '../components/chat/ChatSelectionBar';
import { TurnMetaBadge } from '../components/chat/TurnMetaBadge';
import {
  chatPath,
  decideNewChatDefaults,
  attachmentIndexingNotice,
  codeInterpreterNotice,
  dedupeWarnings,
  describeWarnings,
  parseConversationId,
  resolveInitialSelection,
  resolveNewConversationSelection,
  selectionReducer,
  sendBlockReason,
} from '../components/chat/chatSelection';
import type { ChatMessageModel } from '../components/playground/chatTransport';
import type { ChatSelectionAction } from '../components/chat/chatSelection';
import type { ChatOptions, ChatSelection, ChatSelectionWarning } from '../types/appChat';
import Alert from '../components/ui/Alert';
import { ButtonApp, buttonAppSizeClasses, buttonAppVariantClasses } from '../components/ui/ButtonApp';
import { ButtonLink } from '../components/ui/ButtonLink';
import { LoadingState } from '../components/ui/LoadingState';
import { Title } from '../components/ui/Title';
import { useAppRole } from '../hooks/useAppRole';
import { AppRole } from '../types/roles';

const NO_WARNINGS: readonly ChatSelectionWarning[] = [];

interface AppChatViewProps {
  readonly appId: number;
}

function AppChatView({ appId }: Readonly<AppChatViewProps>) {
  const { t } = useTranslation('common');
  const navigate = useNavigate();
  const { conversationId: conversationParam } = useParams();
  const routeConversationId = parseConversationId(conversationParam);
  const { hasMinRole, loading: roleLoading } = useAppRole(String(appId));

  const [options, setOptions] = useState<ChatOptions | null>(null);
  const [optionsFailed, setOptionsFailed] = useState(false);
  const [selection, dispatchSelection] = useReducer(selectionReducer, null as ChatSelection | null);
  // Route the current `selection` was resolved for; while it differs from the route, sending is blocked.
  const [resolvedRoute, setResolvedRoute] = useState<number | null | undefined>(undefined);
  const [loadWarnings, setLoadWarnings] = useState<readonly ChatSelectionWarning[]>(NO_WARNINGS);
  const [turnWarnings, setTurnWarnings] = useState<readonly ChatSelectionWarning[]>(NO_WARNINGS);
  const [notice, setNotice] = useState<'conversationNotFound' | 'serviceRetired' | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [headerActions, setHeaderActions] = useState<HTMLDivElement | null>(null);
  // Dismissing the attachment-indexing notice lasts for this visit only (component state), so it comes back on
  // the next visit while the condition holds. The dismissed kind is stored, so a different notice still shows.
  const [dismissedIndexingNotice, setDismissedIndexingNotice] = useState<string | null>(null);
  const [dismissedCodeNotice, setDismissedCodeNotice] = useState<string | null>(null);
  const [sidebarToken, setSidebarToken] = useState(0);
  // Remount ChatInterface only when the user moves to another conversation, never when the page itself
  // creates one (the route then catches up with the id the chat already holds). `focus` asks the new
  // instance to put the focus in the composer.
  const createdConversationRef = useRef<number | null>(null);
  const [view, setView] = useState({ route: routeConversationId, key: 0, focus: 0 });
  if (view.route !== routeConversationId) {
    const created = createdConversationRef.current === routeConversationId;
    if (!created) setTurnWarnings(NO_WARNINGS);
    // Browser Back/Forward with the conversations panel open: close it instead of stealing its focus.
    if (!created && panelOpen) setPanelOpen(false);
    setView({
      route: routeConversationId,
      key: created ? view.key : view.key + 1,
      focus: created || panelOpen ? view.focus : view.focus + 1,
    });
  }
  const routeRef = useRef(routeConversationId);
  routeRef.current = routeConversationId;
  // "New conversation" from an opened one: the defaults are being refetched. `token` identifies that request,
  // `pending` is true while the route must not be treated as resolved.
  const newChatRef = useRef({ token: 0, pending: false, touched: false });
  const optionsRef = useRef<ChatOptions | null>(null);
  const viewKeyRef = useRef(view.key);
  viewKeyRef.current = view.key;
  const createdFromKey = view.key;

  // The transport is created once per App; selection and callbacks are read through refs so changing
  // the selection never recreates it (a new transport reloads and blanks the chat).
  const selectionRef = useRef<ChatSelection | null>(selection);
  selectionRef.current = selection;
  optionsRef.current = options;
  /** Selection changes made by the user (not by the page) mark the selection as touched. */
  const userDispatch = useCallback((action: ChatSelectionAction) => {
    newChatRef.current.touched = true;
    dispatchSelection(action);
  }, []);

  const loadOptions = useCallback(async (): Promise<ChatOptions | null> => {
    try {
      const loaded = await apiService.getAppChatOptions(appId);
      setOptions(loaded);
      setOptionsFailed(false);
      return loaded;
    } catch (error) {
      console.error('Error loading chat options:', error);
      setOptionsFailed(true);
      return null;
    }
  }, [appId]);

  const handleTurnEvent = useCallback((event: ChatTurnEvent) => {
    if (event.kind === 'metadata') {
      // A new turn replaces the warnings of the previous one.
      setTurnWarnings(event.warnings);
    } else if (event.warnings.length > 0) {
      setTurnWarnings((previous) => dedupeWarnings([...previous, ...event.warnings]));
    }
  }, []);
  const onTurnEventRef = useRef(handleTurnEvent);
  onTurnEventRef.current = handleTurnEvent;

  const handleTransportError = useCallback(
    (code: ChatTransportErrorCode) => {
      if (code === 'serviceRetired') {
        // Refresh so the retired model is flagged and the user can pick another one.
        setNotice('serviceRetired');
        void loadOptions();
      }
    },
    [loadOptions],
  );
  const onTransportErrorRef = useRef(handleTransportError);
  onTransportErrorRef.current = handleTransportError;

  const transport = useMemo(
    () =>
      createAppChatTransport(appId, () => selectionRef.current, {
        onTurnEvent: (event) => onTurnEventRef.current(event),
        onTransportError: (code) => onTransportErrorRef.current(code),
        // A stream that outlives its conversation view must not write warnings into the next one.
        getContextToken: () => viewKeyRef.current,
      }),
    [appId],
  );

  // Options: one call on entry.
  useEffect(() => {
    void loadOptions();
  }, [loadOptions]);

  // Initial selection: the opened conversation's own, else the user's defaults (FR-10).
  const optionsReady = options !== null;
  useEffect(() => {
    if (!options) return;
    if (routeConversationId !== null && createdConversationRef.current === routeConversationId) {
      // Created by this page: the selection in force is already the right one. Consume the marker so
      // going back to this conversation later loads it like any other.
      createdConversationRef.current = null;
      setResolvedRoute(routeConversationId);
      return;
    }
    if (routeConversationId === null) {
      // Defaults are being refetched after "New": the route is resolved when that settles.
      if (newChatRef.current.pending) return;
      const resolved = resolveNewConversationSelection(options, selectionRef.current, false);
      if (resolved.selection !== selectionRef.current) {
        dispatchSelection({ type: 'replace', selection: resolved.selection });
      }
      setLoadWarnings(resolved.warnings);
      setResolvedRoute(null);
      return;
    }
    let cancelled = false;
    apiService
      .getAppChatConversation(appId, routeConversationId)
      .then((detail) => {
        if (cancelled) return;
        const resolved = resolveInitialSelection(detail.current_selection, options, detail.warnings);
        dispatchSelection({ type: 'replace', selection: resolved.selection });
        setLoadWarnings(resolved.warnings);
        setResolvedRoute(routeConversationId);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        console.error('Error loading chat conversation:', error);
        setNotice('conversationNotFound');
        navigate(chatPath(appId), { replace: true });
      });
    return () => {
      cancelled = true;
    };
    // `options` is deliberately not a dependency: refreshing it (e.g. after a retired model) must not reset the selection.
  }, [optionsReady, routeConversationId, appId, navigate]);

  /** The user moved to another conversation: what belonged to the previous one goes away. */
  const clearTransient = useCallback(() => {
    setNotice(null);
    setTurnWarnings(NO_WARNINGS);
  }, []);

  const handleConversationSelect = useCallback(
    (conversationId: number) => {
      setPanelOpen(false);
      clearTransient();
      createdConversationRef.current = null;
      // Any pending "New" refetch is now stale.
      newChatRef.current = { token: newChatRef.current.token + 1, pending: false, touched: false };
      navigate(chatPath(appId, conversationId));
    },
    [appId, navigate, clearTransient],
  );

  const handleNewConversation = useCallback(() => {
    setPanelOpen(false);
    clearTransient();
    createdConversationRef.current = null;
    const afterOpenedConversation = routeRef.current !== null;
    // Already on the new chat with its defaults still loading: keep that request valid, or nothing would unblock.
    if (!afterOpenedConversation && newChatRef.current.pending) return;
    const token = newChatRef.current.token + 1;
    newChatRef.current = { token, pending: afterOpenedConversation, touched: false };
    navigate(chatPath(appId));
    if (!afterOpenedConversation) return;
    // Defaults, not the selection of the conversation being left; refetched because the backend updates them
    // on every completed turn. If the refetch fails, the options already loaded are used.
    void loadOptions().then((fresh) => {
      const decision = decideNewChatDefaults(
        token,
        newChatRef.current.token,
        routeRef.current === null,
        newChatRef.current.touched,
      );
      if (token === newChatRef.current.token) newChatRef.current.pending = false;
      if (!decision.resolve) return;
      const base = fresh ?? optionsRef.current;
      if (base && decision.applySelection) {
        const resolved = resolveNewConversationSelection(base, null, true);
        dispatchSelection({ type: 'replace', selection: resolved.selection });
        setLoadWarnings(resolved.warnings);
      }
      setResolvedRoute(null);
    });
  }, [appId, navigate, clearTransient, loadOptions]);

  const handleConversationCreated = useCallback(
    (conversationId: number) => {
      // A turn started in a view that has since been replaced must not navigate the user away.
      if (createdFromKey !== viewKeyRef.current) return;
      createdConversationRef.current = conversationId;
      setResolvedRoute(conversationId);
      navigate(chatPath(appId, conversationId), { replace: true });
    },
    [appId, navigate, createdFromKey],
  );

  // One list refresh per turn (a conversation created by the turn is included in it).
  const handleMessageSent = useCallback(() => setSidebarToken((token) => token + 1), []);
  const handleConversationReset = useCallback(() => {
    // The conversation (and its selection) is kept; only its history is gone.
    setTurnWarnings(NO_WARNINGS);
    setNotice(null);
    setSidebarToken((token) => token + 1);
  }, []);

  const focusComposer = useCallback(() => setView((current) => ({ ...current, focus: current.focus + 1 })), []);

  const loadConversations = useCallback(() => apiService.listAppChatConversations(appId), [appId]);
  const renameConversation = useCallback(
    (conversationId: number, title: string) => apiService.renameAppChatConversation(appId, conversationId, title),
    [appId],
  );
  const deleteConversation = useCallback(
    (conversationId: number) => apiService.deleteAppChatConversation(appId, conversationId),
    [appId],
  );

  const renderMessageMeta = useCallback(
    (message: ChatMessageModel) =>
      message.type === 'agent' && (message.turn || message.turnConfig) ? (
        <TurnMetaBadge turn={message.turn} turnConfig={message.turnConfig} />
      ) : null,
    [],
  );

  // A conversation created by this page's own turn is ready even before `resolvedRoute` catches up.
  // The created-conversation marker only counts for a real id: on the new-chat route both sides are null.
  const selectionReady =
    resolvedRoute === routeConversationId ||
    (routeConversationId !== null && createdConversationRef.current === routeConversationId);
  const blockReason = sendBlockReason(options, selection, selectionReady);
  const sendBlockedReason = blockReason ? t(`appChat.blocked.${blockReason}`) : undefined;
  const warningMessages = useMemo(
    () => describeWarnings(dedupeWarnings([...loadWarnings, ...turnWarnings]), options),
    [loadWarnings, turnWarnings, options],
  );

  const toolbarStart = useMemo(
    () =>
      options ? (
        <ChatSelectionBar
          options={options}
          selection={selection}
          dispatch={userDispatch}
          disabled={!selectionReady}
        />
      ) : null,
    [options, selection, selectionReady, userDispatch],
  );

  const conversationsButton = useMemo(
    () => (
      <button
        type="button"
        aria-haspopup="dialog"
        aria-expanded={panelOpen}
        aria-controls={panelOpen ? CONVERSATION_PANEL_ID : undefined}
        onClick={() => setPanelOpen(true)}
        className={`inline-flex cursor-pointer items-center justify-center gap-2 rounded-md font-display font-normal tracking-[-0.02em] transition-colors
                    ${buttonAppSizeClasses.compact} ${buttonAppVariantClasses.secondary}
                    ${panelOpen ? '!bg-surface-hover dark:!bg-surface-hover-dark' : ''}`}
      >
        <MessageSquare className="h-3.5 w-3.5" aria-hidden="true" />
        {t('appChat.page.conversations')}
      </button>
    ),
    [panelOpen, t],
  );

  if (optionsFailed && !options) {
    return (
      <Alert
        type="error"
        title={t('appChat.page.loadErrorTitle')}
        className="mx-auto mt-8 max-w-2xl"
        message={
          <>
            {t('appChat.page.optionsLoadFailed')}
            <span className="mt-4 block">
              <ButtonApp label={t('appChat.page.retry')} variant="danger" size="medium" onClick={() => void loadOptions()} />
            </span>
          </>
        }
      />
    );
  }

  if (!options) {
    return (
      <div className="mx-auto flex max-w-[1680px] flex-col gap-3">
        <Title variant="titSecundario" titulo={t('appChat.page.title')} />
        <LoadingState variant="page" message={t('appChat.page.loading')} />
      </div>
    );
  }

  const noUsableModel = blockReason === 'noUsableModel';
  const dismissNotice = () => {
    setNotice(null);
    focusComposer();
  };
  const currentIndexingNotice = attachmentIndexingNotice(options);
  const indexingNotice = currentIndexingNotice === dismissedIndexingNotice ? null : currentIndexingNotice;
  const currentCodeNotice = codeInterpreterNotice(options, selection);
  const codeNotice = currentCodeNotice === dismissedCodeNotice ? null : currentCodeNotice;
  const dismissCodeNotice = () => {
    setDismissedCodeNotice(currentCodeNotice);
    focusComposer();
  };
  const canConfigureApp = hasMinRole(AppRole.ADMINISTRATOR);
  const dismissIndexingNotice = () => {
    setDismissedIndexingNotice(currentIndexingNotice);
    focusComposer();
  };
  const dismissWarnings = () => {
    setLoadWarnings(NO_WARNINGS);
    setTurnWarnings(NO_WARNINGS);
    focusComposer();
  };

  return (
    <div className="mx-auto flex max-w-[1680px] animate-fade-in flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        {/* Once a conversation exists the subtitle only takes room from the chat. */}
        <Title
          variant="titSecundario"
          titulo={t('appChat.page.title')}
          subtitulo={routeConversationId === null ? t('appChat.page.subtitle') : undefined}
          subtitleMarginBottom={routeConversationId === null ? 20 : 0}
        />
        <div className="flex items-center gap-2">
          {/* "Reset" belongs to the chat; it is drawn here through a portal (`display: contents` keeps the row flat). */}
          <div ref={setHeaderActions} className="contents" />
          {conversationsButton}
        </div>
      </div>

      {noUsableModel && (
        <Alert
          type="warning"
          title={t('appChat.empty.title')}
          message={
            <>
              {/* The wording depends on the role: say nothing until it is known, so it never flashes. */}
              {!roleLoading && t(hasMinRole(AppRole.ADMINISTRATOR) ? 'appChat.empty.messageAdmin' : 'appChat.empty.messageMember')}
              {!roleLoading && hasMinRole(AppRole.ADMINISTRATOR) && (
                <span className="mt-3 block">
                  <ButtonLink
                    label={t('appChat.empty.configureLink')}
                    to={`/apps/${appId}/settings/ai-services`}
                    variant="secondary"
                    size="compact"
                  />
                </span>
              )}
            </>
          }
        />
      )}
      {indexingNotice && (
        <Alert
          type="info"
          title={t('appChat.attachmentIndexing.title')}
          message={
            <>
              {t(`appChat.attachmentIndexing.${indexingNotice}`)}{' '}
              {roleLoading ? null : canConfigureApp ? (
                <span className="mt-3 block">
                  <ButtonLink
                    label={t('appChat.attachmentIndexing.configureLink')}
                    to={`/apps/${appId}/settings`}
                    variant="secondary"
                    size="compact"
                  />
                </span>
              ) : (
                t('appChat.attachmentIndexing.askAdmin')
              )}
            </>
          }
          onDismiss={dismissIndexingNotice}
          dismissAriaLabel={t('alert.dismissNamed', { name: t('appChat.attachmentIndexing.title') })}
        />
      )}
      {codeNotice && (
        <Alert
          type="info"
          title={t('appChat.codeInterpreter.title')}
          message={
            <>
              {t(`appChat.codeInterpreter.${codeNotice}`)}{' '}
              {/* The administrator of the platform fixes these; neither a link nor "ask an admin" helps. */}
              {codeNotice === 'providerUnavailable' || codeNotice === 'unavailable' || roleLoading ? null : canConfigureApp ? (
                <span className="mt-3 block">
                  <ButtonLink
                    label={t('appChat.attachmentIndexing.configureLink')}
                    to={`/apps/${appId}/settings`}
                    variant="secondary"
                    size="compact"
                  />
                </span>
              ) : (
                t('appChat.attachmentIndexing.askAdmin')
              )}
            </>
          }
          onDismiss={dismissCodeNotice}
          dismissAriaLabel={t('alert.dismissNamed', { name: t('appChat.codeInterpreter.title') })}
        />
      )}
      {notice && (
        <Alert
          type={notice === 'serviceRetired' ? 'error' : 'warning'}
          // The failed turn already shows its own role=alert error in the conversation: announcing this one
          // assertively too would read the same news twice.
          polite={notice === 'serviceRetired'}
          message={t(`appChat.notices.${notice}`)}
          onDismiss={dismissNotice}
          dismissAriaLabel={t('alert.dismissNamed', { name: t('appChat.notices.label') })}
        />
      )}
      {warningMessages.length > 0 && (
        // role=alert (default for warnings): announced even though it mounts with its content.
        <Alert
          type="warning"
          title={t('appChat.warnings.title')}
          message={
            <ul className="list-disc pl-5">
              {warningMessages.map((warning) => (
                <li key={`${warning.key}-${warning.values.name ?? ''}`}>
                  {t(`appChat.warnings.${warning.key}`, warning.values)}
                </li>
              ))}
            </ul>
          }
          onDismiss={dismissWarnings}
          dismissAriaLabel={t('alert.dismissNamed', { name: t('appChat.warnings.title') })}
        />
      )}

      <div className="flex">
        <ConversationSidebar
          loadConversations={loadConversations}
          renameConversation={renameConversation}
          deleteConversation={deleteConversation}
          refreshToken={sidebarToken}
          currentConversationId={routeConversationId}
          onConversationSelect={handleConversationSelect}
          onNewConversation={handleNewConversation}
          open={panelOpen}
          onClose={() => setPanelOpen(false)}
        />
        <div className="min-w-0 flex-1">
          <ChatInterface
            key={view.key}
            appId={appId}
            transport={transport}
            agentName={t('appChat.page.assistantName')}
            conversationId={routeConversationId}
            onConversationCreated={handleConversationCreated}
            onConversationReset={handleConversationReset}
            onMessageSent={handleMessageSent}
            onDetachedTurnFinished={handleMessageSent}
            toolbarStart={toolbarStart}
            resetButtonTarget={headerActions}
            wide
            cardHeightClassName={routeConversationId === null ? 'sm:h-[calc(100vh-15rem)]' : 'sm:h-[calc(100vh-12rem)]'}
            renderMessageMeta={renderMessageMeta}
            sendBlockedReason={sendBlockedReason}
            focusComposerSignal={view.focus}
          />
        </div>
      </div>
    </div>
  );
}

/** Per-App Chat. Keyed by App so navigating to another App never shows the previous App's state. */
function AppChatPage() {
  const { appId } = useParams();
  const parsed = appId ? Number.parseInt(appId, 10) : Number.NaN;
  if (Number.isNaN(parsed)) return null;
  return <AppChatView key={parsed} appId={parsed} />;
}

export default AppChatPage;
