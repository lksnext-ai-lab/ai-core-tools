export type StreamingMessageKey =
  | 'thinking'
  | 'searching_knowledge_base'
  | 'using_external_tool'
  | 'consulting_agent'
  | 'running_code'
  | 'generating_image'
  | 'searching_web'
  | 'processing_file'
  | 'downloading_file'
  | 'loading_skill'
  | 'getting_date'
  | 'using_tool'
  | 'stream_error'
  | 'stream_aborted';

type StreamingTranslations = Record<StreamingMessageKey, string>;

const translations: Record<string, StreamingTranslations> = {
  en: {
    thinking: 'Thinking...',
    searching_knowledge_base: 'Searching knowledge base...',
    using_external_tool: 'Using external tool...',
    consulting_agent: 'Consulting {name}...',
    running_code: 'Running code...',
    generating_image: 'Generating image...',
    searching_web: 'Searching the web...',
    processing_file: 'Processing file...',
    downloading_file: 'Downloading file...',
    loading_skill: 'Loading skill...',
    getting_date: 'Getting current date...',
    using_tool: 'Using {name}...',
    stream_error: 'An error occurred while streaming',
    stream_aborted: 'Response was cancelled',
  },
};

// Default language
let currentLang = 'en';

export function setStreamingLanguage(lang: string): void {
  if (translations[lang]) {
    currentLang = lang;
  }
}

export function getStreamingMessage(
  key: StreamingMessageKey,
  params?: Record<string, string>,
): string {
  const message =
    translations[currentLang]?.[key] ?? translations['en'][key] ?? key;
  if (!params) return message;
  return Object.entries(params).reduce(
    (msg, [k, v]) => msg.replace(`{${k}}`, v),
    message,
  );
}

export { translations as streamingTranslations };
