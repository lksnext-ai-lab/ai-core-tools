import type { OutputContentMode, OutputDestination } from '../../services/api';

export type ProviderKey = 'teams_workflow' | 'webhook';
export type AuthMode = 'hmac_sha256' | 'bearer' | 'none';

export function contentModeLabels(provider: ProviderKey): Record<OutputContentMode, string> {
  return {
    result: provider === 'webhook' ? 'Resultado (hasta 100.000 caracteres)' : 'Resultado (hasta 5.000 caracteres)',
    excerpt: provider === 'webhook' ? 'Extracto (hasta 4.000 caracteres)' : 'Extracto (hasta 1.200 caracteres)',
    link_only: 'Sólo enlace',
  };
}

export interface OutputChannelForm {
  name: string;
  provider: ProviderKey;
  url: string;
  authMode: AuthMode;
  credential: string;
  includeAttachments: boolean;
  receiverDeduplicates: boolean;
  contentMode: OutputContentMode;
}

export function initialChannelForm(destination: OutputDestination | null): OutputChannelForm {
  return {
    name: destination?.name ?? '',
    provider: destination?.provider_key === 'webhook' ? 'webhook' : 'teams_workflow',
    url: '',
    authMode: (destination?.public_config.auth_mode as AuthMode) ?? 'hmac_sha256',
    credential: '',
    includeAttachments: Boolean(destination?.public_config.include_attachments),
    receiverDeduplicates: Boolean(destination?.public_config.receiver_deduplicates),
    contentMode: destination?.content_mode ?? 'result',
  };
}

export function validateChannelIdentity(form: OutputChannelForm, existing: OutputDestination[], destination: OutputDestination | null): string | null {
  if (!form.name.trim()) return 'Indica el nombre del canal.';
  if (form.name.trim().length > 255) return 'El nombre puede tener hasta 255 caracteres.';
  if (existing.some((item) => item.id !== destination?.id && item.name === form.name.trim())) {
    return 'Ya existe un canal con este nombre.';
  }
  return null;
}

export function validateChannelConfiguration(form: OutputChannelForm, destination: OutputDestination | null): string | null {
  if (!['result', 'excerpt', 'link_only'].includes(form.contentMode)) return 'Selecciona un modo de contenido válido.';
  if (!destination || (form.provider === 'teams_workflow' && form.url.trim())) {
    try {
      const url = new URL(form.url.trim());
      if (url.protocol !== 'https:' || (url.port && url.port !== '443') || url.username || url.password || url.hash) {
        return 'Usa una URL HTTPS en el puerto 443, sin usuario, contraseña ni fragmento.';
      }
    } catch {
      return 'Indica una URL HTTPS válida.';
    }
  }
  if (form.provider !== 'webhook' || form.authMode === 'none') return null;
  const credential = form.credential.trim();
  const credentialRequired = !destination || !destination.has_credentials || destination.public_config.auth_mode !== form.authMode;
  if (!credential) return credentialRequired ? 'Indica la credencial de autenticación del webhook.' : null;
  if (form.authMode === 'hmac_sha256') {
    try {
      if (!/^[A-Za-z0-9+/]+={0,2}$/.test(credential) || atob(credential).length !== 32 || credential.length % 4 !== 0) {
        return 'La clave HMAC debe estar en Base64 y contener exactamente 32 bytes.';
      }
    } catch {
      return 'La clave HMAC debe estar en Base64 y contener exactamente 32 bytes.';
    }
  } else if (credential.length > 4096 || !/^[\x21-\x7e]+$/.test(credential)) {
    return 'El token debe contener caracteres ASCII imprimibles, sin espacios (máximo 4096).';
  }
  return null;
}

export function buildChannelPayload(form: OutputChannelForm, destination: OutputDestination | null) {
  const credentials: Record<string, string> | undefined = form.provider === 'webhook' && form.authMode !== 'none' && form.credential.trim()
    ? form.authMode === 'hmac_sha256'
      ? { signing_secret: form.credential.trim() }
      : { bearer_token: form.credential.trim() }
    : undefined;
  return {
    name: form.name.trim(),
    content_mode: form.contentMode,
    ...(!destination ? { provider_key: form.provider, webhook_url: form.url.trim() }
      : form.provider === 'teams_workflow' && form.url.trim() ? { webhook_url: form.url.trim() } : {}),
    ...(form.provider === 'webhook' ? {
      public_config: {
        ...destination?.public_config,
        auth_mode: form.authMode,
        include_attachments: form.includeAttachments,
        receiver_deduplicates: form.receiverDeduplicates,
      },
      ...(credentials ? { credentials } : {}),
      ...(destination && form.authMode === 'none' ? { clear_credentials: true } : {}),
    } : {}),
  };
}
