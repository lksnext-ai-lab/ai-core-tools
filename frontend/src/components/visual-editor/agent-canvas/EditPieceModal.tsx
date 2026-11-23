import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { apiService } from '../../../services/api';
import { useApiMutation } from '../../../hooks/useApiMutation';
import { useSettingsCache } from '../../../contexts/SettingsCacheContext';
import { useTranslation } from 'react-i18next';
import { errorMessage } from '../../../constants/messages';
import type { SandboxServiceFormData, ServiceFormData } from '../../../types/services';
import Modal from '../../ui/Modal';
import { LoadingState } from '../../ui/LoadingState';
import Alert from '../../ui/Alert';
import SkillForm from '../../forms/SkillForm';
import MCPConfigForm from '../../forms/MCPConfigForm';
import DataStructureForm from '../../forms/DataStructureForm';
import MiddlewareForm from '../../forms/MiddlewareForm';
import CompactServiceEditor from '../../services/CompactServiceEditor';
import type { PieceKind } from './agentPorts';
import type { CanvasPiece } from './useAgentCanvasData';

export interface EditPieceModalProps {
  readonly appId: number;
  /** The piece being edited; `kind` picks the form, `id` the record. */
  readonly piece: CanvasPiece;
  readonly onClose: () => void;
  /** Called after a successful save so the caller closes the modal and refetches. */
  readonly onSaved: () => void;
}

/** Kinds this overlay edits; the rest (AI services, silos, agents) have their own paths. */
const EDITABLE_KINDS: ReadonlySet<PieceKind> = new Set([
  'skill',
  'mcp',
  'middleware',
  'embedding',
  'sandbox',
  'parser',
]);

/** Kinds with a dedicated edit title; the rest fall back to the generic one. */
const TITLED_KINDS: ReadonlySet<PieceKind> = new Set(['skill', 'mcp', 'middleware', 'parser']);

/**
 * Edit overlay opened from the canvas inspector: reuses each piece's own
 * settings-page form (the service editor for embedding and sandbox services)
 * and saves through the same API calls, so the change lands outside the
 * editor too. Stays on top of the canvas instead of navigating away.
 */
export function EditPieceModal({ appId, piece, onClose, onSaved }: Readonly<EditPieceModalProps>) {
  const { t } = useTranslation('common');
  const mutate = useApiMutation();
  const entityName = (k: PieceKind): string => t(`agentCanvas.createPiece.entity.${k}`);
  const settingsCache = useSettingsCache();
  // `any` on purpose: the fetched detail feeds each form's own prop shape,
  // which its local interface under-declares (as the settings pages do).
  const [detail, setDetail] = useState<any>(null);
  const [failed, setFailed] = useState(false);

  const kind = piece.kind;
  const editable = EDITABLE_KINDS.has(kind);

  useEffect(() => {
    if (!editable) return;
    let cancelled = false;
    setDetail(null);
    setFailed(false);
    (async () => {
      try {
        const fetched = await (kind === 'skill'
          ? apiService.getSkill(appId, piece.id)
          : kind === 'mcp'
            ? apiService.getMCPConfig(appId, piece.id)
            : kind === 'middleware'
              ? apiService.getMiddleware(appId, piece.id)
              : kind === 'parser'
                ? apiService.getOutputParser(appId, piece.id)
                : kind === 'embedding'
                  ? apiService.getEmbeddingService(appId, piece.id)
                  : apiService.getSandboxService(appId, piece.id));
        if (!cancelled) setDetail(fetched);
      } catch (err) {
        if (cancelled) return;
        toast.error(errorMessage(err, t('agentCanvas.editPiece.loadFailed', { entity: entityName(kind) })));
        setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [appId, kind, piece.id, editable, t]);

  /** Drops the settings-cache list this kind's settings page reads, so it reloads with the change. */
  function invalidateSettingsCache(): void {
    const id = String(appId);
    switch (kind) {
      case 'embedding':
        settingsCache.invalidateEmbeddingServices(id);
        return;
      case 'sandbox':
        settingsCache.invalidateSandboxServices(id);
        return;
      case 'skill':
        settingsCache.invalidateSkills(id);
        return;
      case 'mcp':
        settingsCache.invalidateMCPConfigs(id);
        return;
      case 'parser':
        settingsCache.invalidateDataStructures(id);
        return;
      default:
        // Middlewares have no cached settings list.
        return;
    }
  }

  /** Saves through the same toast-wrapped mutation the settings pages use, then reports the save. */
  async function save(label: string, update: () => Promise<unknown>): Promise<void> {
    const updated = await mutate(update, {
      loading: t('agentCanvas.editPiece.updating', { entity: label }),
      success: t('agentCanvas.editPiece.updated', { entity: label.charAt(0).toUpperCase() + label.slice(1) }),
      error: (err) => errorMessage(err, t('agentCanvas.editPiece.saveFailed', { entity: label })),
    });
    if (updated === undefined) return;
    invalidateSettingsCache();
    onSaved();
  }

  if (!editable) return null;

  const title = TITLED_KINDS.has(kind) ? t(`agentCanvas.editPiece.title.${kind}`) : t('agentCanvas.editPiece.title.service');

  if (kind === 'embedding' || kind === 'sandbox') {
    if (detail) {
      return (
        <CompactServiceEditor
          isOpen
          kind={kind === 'embedding' ? 'embedding' : 'sandbox'}
          scope="app"
          appId={appId}
          service={detail}
          onClose={onClose}
          onSave={(data: ServiceFormData | SandboxServiceFormData) =>
            save(entityName(kind), () =>
              kind === 'embedding'
                ? apiService.updateEmbeddingService(appId, piece.id, data)
                : apiService.updateSandboxService(appId, piece.id, data),
            )
          }
        />
      );
    }
    return (
      <Modal isOpen onClose={onClose} title={title}>
        <LoadingOrFailed failed={failed} label={entityName(kind)} />
      </Modal>
    );
  }

  return (
    <Modal isOpen onClose={onClose} title={title} size={kind === 'parser' ? 'xlarge' : 'large'}>
      {detail && kind === 'skill' && (
        <SkillForm
          skill={detail}
          onSubmit={(data) => save(entityName('skill'), () => apiService.updateSkill(appId, piece.id, data))}
          onCancel={onClose}
        />
      )}
      {detail && kind === 'mcp' && (
        <MCPConfigForm
          mcpConfig={detail}
          onSubmit={(data) => save(entityName('mcp'), () => apiService.updateMCPConfig(appId, piece.id, data))}
          onCancel={onClose}
        />
      )}
      {detail && kind === 'middleware' && (
        <MiddlewareForm
          middleware={detail}
          appId={appId}
          onSubmit={(data) => save(entityName('middleware'), () => apiService.updateMiddleware(appId, piece.id, data))}
          onCancel={onClose}
        />
      )}
      {detail && kind === 'parser' && (
        <DataStructureForm
          dataStructure={detail}
          onSubmit={(data) => save(entityName('parser'), () => apiService.updateOutputParser(appId, piece.id, data))}
          onCancel={onClose}
        />
      )}
      {!detail && <LoadingOrFailed failed={failed} label={entityName(kind)} />}
    </Modal>
  );
}

function LoadingOrFailed({ failed, label }: { readonly failed: boolean; readonly label: string }) {
  const { t } = useTranslation('common');
  if (failed) {
    return <Alert type="error" message={t('agentCanvas.editPiece.failedToLoad', { entity: label })} />;
  }
  return <LoadingState variant="inline" message={t('agentCanvas.editPiece.loading', { entity: label })} />;
}
