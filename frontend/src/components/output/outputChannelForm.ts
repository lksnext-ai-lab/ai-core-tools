import type { OutputContentMode, OutputDestination } from '../../services/api';
import type { TFunction } from 'i18next';

export type ProviderKey = 'teams_workflow' | 'webhook';
export type AuthMode = 'hmac_sha256' | 'bearer' | 'none';

export function contentModeLabels(provider: ProviderKey, t: TFunction<'common'>): Record<OutputContentMode, string> {
  const isWebhook = provider === 'webhook';
  return {
    result: t('outputDestinationsPage.contentModes.result', { maxCharacters: isWebhook ? 100000 : 5000 }),
    excerpt: t('outputDestinationsPage.contentModes.excerpt', { maxCharacters: isWebhook ? 4000 : 1200 }),
    link_only: t('outputDestinationsPage.contentModes.link_only'),
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

export type ChannelFieldErrors = Partial<Record<'name' | 'contentMode' | 'url' | 'credential', string>>;

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

export function validateChannelIdentity(form: OutputChannelForm, existing: OutputDestination[], destination: OutputDestination | null, t: TFunction<'common'>): ChannelFieldErrors | null {
  if (!form.name.trim()) return { name: t('outputChannelWizard.validation.nameRequired') };
  if (form.name.trim().length > 255) return { name: t('outputChannelWizard.validation.nameMaxLength') };
  if (existing.some((item) => item.id !== destination?.id && item.name === form.name.trim())) {
    return { name: t('outputChannelWizard.validation.nameDuplicate') };
  }
  return null;
}

export function validateChannelConfiguration(form: OutputChannelForm, destination: OutputDestination | null, t: TFunction<'common'>): ChannelFieldErrors | null {
  if (!['result', 'excerpt', 'link_only'].includes(form.contentMode)) return { contentMode: t('outputChannelWizard.validation.contentMode') };
  if (!destination || (form.provider === 'teams_workflow' && form.url.trim())) {
    try {
      const url = new URL(form.url.trim());
      if (url.protocol !== 'https:' || (url.port && url.port !== '443') || url.username || url.password || url.hash) {
        return { url: t('outputChannelWizard.validation.urlHttps') };
      }
    } catch {
      return { url: t('outputChannelWizard.validation.urlInvalid') };
    }
  }
  if (form.provider !== 'webhook' || form.authMode === 'none') return null;
  const credential = form.credential.trim();
  const credentialRequired = !destination || !destination.has_credentials || destination.public_config.auth_mode !== form.authMode;
  if (!credential) return credentialRequired ? { credential: t('outputChannelWizard.validation.credentialRequired') } : null;
  if (form.authMode === 'hmac_sha256') {
    try {
      if (!/^[A-Za-z0-9+/]+={0,2}$/.test(credential) || atob(credential).length !== 32 || credential.length % 4 !== 0) {
        return { credential: t('outputChannelWizard.validation.hmacKey') };
      }
    } catch {
      return { credential: t('outputChannelWizard.validation.hmacKey') };
    }
  } else if (credential.length > 4096 || !/^[\x21-\x7e]+$/.test(credential)) {
    return { credential: t('outputChannelWizard.validation.bearerToken') };
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
