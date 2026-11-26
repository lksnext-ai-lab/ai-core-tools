import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { apiService, type Agent, type DataStructure } from '../../../services/api';
import { useApiMutation } from '../../../hooks/useApiMutation';
import { useSettingsCache } from '../../../contexts/SettingsCacheContext';
import { useTranslation } from 'react-i18next';
import { errorMessage } from '../../../constants/messages';
import type { LifecycleStatus, SandboxServiceFormData, ServiceFormData } from '../../../types/services';
import Modal from '../../ui/Modal';
import { LoadingState } from '../../ui/LoadingState';
import SiloForm from '../../forms/SiloForm';
import SkillForm from '../../forms/SkillForm';
import MCPConfigForm from '../../forms/MCPConfigForm';
import DataStructureForm from '../../forms/DataStructureForm';
import MiddlewareForm from '../../forms/MiddlewareForm';
import AgentQuickCreateForm from '../../forms/AgentQuickCreateForm';
import ServiceWizard from '../../services/wizard/ServiceWizard';
import type { PieceKind } from './agentPorts';

export interface CreatePieceModalProps {
  readonly appId: number;
  /** The palette category the «+» was pressed on; decides which existing creation form opens. */
  readonly kind: PieceKind;
  readonly onClose: () => void;
  /** Called once the piece is saved. The caller closes the modal and connects the piece. */
  readonly onCreated?: (
    kind: PieceKind,
    id: number,
    name: string,
    lifecycleStatus?: LifecycleStatus,
    /** AI services only: whether the created service can analyse video. */
    supportsVideo?: boolean,
  ) => void;
}

interface CreatedPiece {
  readonly id: number;
  readonly name: string;
  /** Services only: the lifecycle status the create response reports. */
  readonly lifecycleStatus?: LifecycleStatus;
  /** AI services only: whether the created service can analyse video. */
  readonly supportsVideo?: boolean;
}

/**
 * Creation modal opened from a palette «+». Reuses the forms and save calls of
 * each piece's own settings page: the service wizard for AI, embedding and
 * sandbox services, and the existing forms for the rest. (Editing an AI
 * service from the canvas opens CompactServiceEditor in AgentCanvas instead.)
 */
export function CreatePieceModal({ appId, kind, onClose, onCreated }: Readonly<CreatePieceModalProps>) {
  const { t } = useTranslation('common');
  const mutate = useApiMutation();
  const entityName = (k: PieceKind): string => t(`agentCanvas.createPiece.entity.${k}`);
  const settingsCache = useSettingsCache();
  const [blankParser, setBlankParser] = useState<DataStructure | null>(null);

  // Output parsers need the blank structure (with the parser options) before the form can open.
  useEffect(() => {
    if (kind !== 'parser') return;
    let cancelled = false;
    apiService
      .getOutputParser(appId, 0)
      .then((blank) => {
        if (!cancelled) setBlankParser(blank);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        toast.error(errorMessage(err, t('agentCanvas.createPiece.parserLoadFailed')));
        onClose();
      });
    return () => {
      cancelled = true;
    };
  }, [appId, kind, onClose, t]);

  /** Drops the settings-cache list this kind's settings page reads, so it reloads with the new piece. */
  function invalidateSettingsCache(): void {
    const id = String(appId);
    switch (kind) {
      case 'ai_service':
        settingsCache.invalidateAIServices(id);
        return;
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
        // Silos, middlewares and agents have no cached settings list.
        return;
    }
  }

  /** Saves through the same toast-wrapped mutation the settings pages use, then reports the new piece. */
  async function save<T>(label: string, create: () => Promise<T>, pick: (created: T) => CreatedPiece): Promise<void> {
    const created = await mutate(create, {
      loading: t('agentCanvas.createPiece.creating', { entity: label }),
      success: t('agentCanvas.createPiece.created', { entity: label.charAt(0).toUpperCase() + label.slice(1) }),
      error: (err) => errorMessage(err, t('agentCanvas.createPiece.saveFailed', { entity: label })),
    });
    if (created === undefined) return;
    invalidateSettingsCache();
    const piece = pick(created);
    onCreated?.(kind, piece.id, piece.name, piece.lifecycleStatus, piece.supportsVideo);
  }

  async function saveService(data: ServiceFormData | SandboxServiceFormData): Promise<void> {
    if (kind === 'ai_service') {
      await save(
        entityName('ai_service'),
        () => apiService.createAIService(appId, data),
        (service) => ({
          id: service.service_id,
          name: service.name,
          lifecycleStatus: service.lifecycle_status,
          supportsVideo: service.supports_video,
        }),
      );
    } else if (kind === 'embedding') {
      await save(
        entityName('embedding'),
        () => apiService.createEmbeddingService(appId, data),
        (service) => ({ id: service.service_id, name: service.name, lifecycleStatus: service.lifecycle_status }),
      );
    } else {
      await save(
        entityName('sandbox'),
        () => apiService.createSandboxService(appId, data),
        (service) => ({ id: service.service_id, name: service.name, lifecycleStatus: service.lifecycle_status }),
      );
    }
  }

  switch (kind) {
    case 'ai_service':
      return (
        <ServiceWizard isOpen kind="ai" scope="app" appId={appId} onClose={onClose} onSave={saveService} />
      );

    case 'embedding':
    case 'sandbox':
      return (
        <ServiceWizard isOpen kind={kind} scope="app" appId={appId} onClose={onClose} onSave={saveService} />
      );

    case 'silo':
      return (
        <Modal isOpen onClose={onClose} title={t('agentCanvas.createPiece.title.silo')} size="xlarge">
          <SiloForm
            onSubmit={(data) =>
              save(
                entityName('silo'),
                () => apiService.createSilo(appId, data),
                (silo) => ({ id: silo.silo_id, name: silo.name }),
              )
            }
            onCancel={onClose}
          />
        </Modal>
      );

    case 'skill':
      return (
        <Modal isOpen onClose={onClose} title={t('agentCanvas.createPiece.title.skill')} size="large">
          <SkillForm
            skill={null}
            onSubmit={(data) =>
              save(
                entityName('skill'),
                () => apiService.createSkill(appId, data),
                (skill) => ({ id: skill.skill_id, name: skill.name }),
              )
            }
            onCancel={onClose}
          />
        </Modal>
      );

    case 'mcp':
      return (
        <Modal isOpen onClose={onClose} title={t('agentCanvas.createPiece.title.mcp')}>
          <MCPConfigForm
            mcpConfig={null}
            onSubmit={(data) =>
              save(
                entityName('mcp'),
                () => apiService.createMCPConfig(appId, data),
                (config) => ({ id: config.config_id, name: config.name }),
              )
            }
            onCancel={onClose}
          />
        </Modal>
      );

    case 'parser':
      return (
        <Modal isOpen onClose={onClose} title={t('agentCanvas.createPiece.title.parser')} size="xlarge">
          {blankParser ? (
            <DataStructureForm
              dataStructure={{
                ...blankParser,
                fields: blankParser.fields ?? [],
                available_parsers: blankParser.available_parsers ?? [],
              }}
              onSubmit={(data) =>
                save(
                  entityName('parser'),
                  () => apiService.createOutputParser(appId, data),
                  (parser) => ({ id: parser.parser_id, name: parser.name }),
                )
              }
              onCancel={onClose}
            />
          ) : (
            <LoadingState variant="inline" message={t('agentCanvas.createPiece.loading', { entity: entityName('parser') })} />
          )}
        </Modal>
      );

    case 'middleware':
      return (
        <Modal isOpen onClose={onClose} title={t('agentCanvas.createPiece.title.middleware')} size="large">
          <MiddlewareForm
            middleware={null}
            appId={appId}
            onSubmit={(data) =>
              save(
                entityName('middleware'),
                () => apiService.createMiddleware(appId, data),
                (middleware) => ({ id: middleware.middleware_id, name: middleware.name }),
              )
            }
            onCancel={onClose}
          />
        </Modal>
      );

    case 'agent':
      return (
        <Modal isOpen onClose={onClose} title={t('agentCanvas.createPiece.title.agent')} size="medium">
          <AgentQuickCreateForm
            appId={appId}
            mode="modal"
            onCreated={(agent: Agent) => onCreated?.(kind, agent.agent_id, agent.name)}
            onCancel={onClose}
          />
        </Modal>
      );
  }
}
