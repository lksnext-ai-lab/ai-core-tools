import React, { createContext, useContext, useMemo, useState } from 'react';
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown';
import { useTranslation } from 'react-i18next';
import remarkGfm from 'remark-gfm';
import InlineFileImage from './InlineFileImage';
import InlineFileDownload from './InlineFileDownload';
import { markdownUrlTransform, isAutoLoadableImageUrl, urlHost } from '../../utils/markdownUrls';

interface MessageContentProps {
  content: string | object;
  resolveFileUrl?: (fileId: string) => Promise<string>;
}

const IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg']);
const ResolveFileUrlContext = createContext<((fileId: string) => Promise<string>) | undefined>(undefined);

function isImageFilename(filename: string): boolean {
  const ext = filename.toLowerCase().lastIndexOf('.');
  return ext !== -1 && IMAGE_EXTENSIONS.has(filename.toLowerCase().slice(ext));
}

const markdownPatterns = [
  /^#\s/, // Headers
  /\*\*.*\*\*/, // Bold
  /\*.*\*/, // Italic
  /\[.*\]\(.*\)/, // Links
  /```[\s\S]*```/, // Code blocks
  /`.*`/, // Inline code
  /^\s*[-*+]\s/, // Lists
  /^\s*\d+\.\s/, // Numbered lists
  /^\s*>\s/, // Blockquotes
  /\|.*\|.*\|/, // Tables
];

function isJson(str: string): boolean {
  try {
    JSON.parse(str);
    return true;
  } catch {
    return false;
  }
}

function isMarkdown(str: string): boolean {
  return markdownPatterns.some(pattern => pattern.test(str));
}

function formatJson(jsonStr: string, invalidJsonMessage: string): React.ReactNode {
  try {
    const parsed = JSON.parse(jsonStr);
    return (
      <pre className="bg-white dark:bg-black p-4 whitespace-pre-wrap" style={{ overflowWrap: 'anywhere', wordBreak: 'normal'}}>
        <code className="text-sm">
          {JSON.stringify(parsed, null, 2)}
        </code>
      </pre>
    );
  } catch {
    return <span className="text-red-500">{invalidJsonMessage}</span>;
  }
}

function MarkdownCode({ className, children, ...props }: any) {
  const { t } = useTranslation('common');
  const match = /language-(\w+)/.exec(className || '');
  const isInline = !match;
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    const text = typeof children === 'string' ? children : String(children);
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }).catch(() => {
      // ignore: nothing was copied, so no confirmation is shown
    });
  };

  return isInline ? (
    <code className="bg-canvas-alt dark:bg-canvas-alt-dark text-fg-secondary dark:text-fg-secondary-dark px-1 py-0.5 rounded text-sm" {...props}>{children}</code>
  ) : (
    <div className="relative group">
      <button
        onClick={handleCopy}
        aria-label={t('messageContent.copyCode')}
        className="absolute top-2 right-2 inline-flex cursor-pointer items-center justify-center gap-2 p-1.5 font-display font-normal tracking-[-0.02em] transition-colors rounded-md border border-ink bg-surface text-fg hover:bg-surface-hover dark:border-ink-dark dark:bg-surface-dark dark:text-fg-dark dark:hover:bg-surface-hover-dark opacity-0 group-hover:opacity-100 focus:opacity-100"
      >
        {copied ? (
          <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        ) : (
          <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
          </svg>
        )}
      </button>
      <pre className="bg-ink text-ink-on p-4 pr-12 rounded-md overflow-x-auto dark:border dark:border-line-dark dark:bg-canvas-dark dark:text-fg-dark">
        <code className={className} {...props}>{children}</code>
      </pre>
    </div>
  );
}

function MarkdownImage({ src, alt }: any) {
  const { t } = useTranslation('common');
  const resolveFileUrl = useContext(ResolveFileUrlContext);
  if (!src) return null;
  if (src?.startsWith('file://') && resolveFileUrl) {
    const fileId = src.slice('file://'.length);
    const filename = alt || fileId;
    return <InlineFileImage fileId={fileId} filename={filename} resolveUrl={resolveFileUrl} />;
  }
  if (isAutoLoadableImageUrl(src)) {
    return <img src={src} alt={alt} className="max-w-full rounded" />;
  }
  // Model output can be steered by prompt injection; auto-loading a third-party
  // image would leak data through its URL with zero clicks, so link to it instead.
  return (
    <a href={src} className="text-sm text-fg underline decoration-accent dark:text-fg-dark dark:decoration-accent-dark inline-block"
      target="_blank" rel="noopener noreferrer nofollow">
      🖼 {alt || t('messageContent.externalImage')}{urlHost(src) && ` (${urlHost(src)})`}
    </a>
  );
}

function MarkdownLink({ children, href, ...props }: any) {
  const resolveFileUrl = useContext(ResolveFileUrlContext);
  if (href?.startsWith('file://') && resolveFileUrl) {
    const fileId = href.slice('file://'.length);
    const filename = typeof children === 'string'
      ? children.replace(/^📎\s*/, '').trim()
      : fileId;
    if (isImageFilename(filename)) {
      return <InlineFileImage fileId={fileId} filename={filename} resolveUrl={resolveFileUrl} />;
    }
    return <InlineFileDownload fileId={fileId} filename={filename} resolveUrl={resolveFileUrl} />;
  }
  return (
    <a href={href} className="text-fg underline decoration-accent dark:text-fg-dark dark:decoration-accent-dark"
      target="_blank" rel="noopener noreferrer" {...props}>
      {children}
    </a>
  );
}

function MarkdownH1({ children, ...props }: any) {
  return <h1 className="text-2xl font-bold mb-4 mt-6" {...props}>{children}</h1>;
}

function MarkdownH2({ children, ...props }: any) {
  return <h2 className="text-xl font-bold mb-3 mt-5" {...props}>{children}</h2>;
}

function MarkdownH3({ children, ...props }: any) {
  return <h3 className="text-lg font-bold mb-2 mt-4" {...props}>{children}</h3>;
}

function MarkdownUl({ children, ...props }: any) {
  return <ul className="list-disc list-inside mb-4 space-y-1" {...props}>{children}</ul>;
}

function MarkdownOl({ children, ...props }: any) {
  return <ol className="list-decimal list-inside mb-4 space-y-1" {...props}>{children}</ol>;
}

function MarkdownBlockquote({ children, ...props }: any) {
  return (
    <blockquote className="border-l-4 border-accent dark:border-accent-dark pl-4 italic text-fg dark:text-fg-dark mb-4" {...props}>
      {children}
    </blockquote>
  );
}

function MarkdownTable({ children, ...props }: any) {
  return (
    <div className="mb-4 bg-surface border border-line rounded-lg overflow-visible dark:bg-surface-dark dark:border-line-dark">
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-line dark:divide-line-dark" {...props}>
          {children}
        </table>
      </div>
    </div>
  );
}

function MarkdownTableHead({ children, ...props }: any) {
  return <thead className="bg-tableCab dark:bg-tableCab-dark" {...props}>{children}</thead>;
}

function MarkdownTableBody({ children, ...props }: any) {
  return (
    <tbody className="bg-surface divide-y divide-line text-sm text-fg dark:bg-surface-dark dark:divide-line-dark dark:text-fg-dark" {...props}>
      {children}
    </tbody>
  );
}

function MarkdownTableRow({ children, ...props }: any) {
  return <tr className="hover:bg-surface-tint dark:hover:bg-surface-tint-dark" {...props}>{children}</tr>;
}

function MarkdownTh({ children, ...props }: any) {
  return <th className="px-6 py-3 text-left text-[11px] font-medium text-fg-tertiary uppercase tracking-[0.05em] dark:text-fg-tertiary-dark" {...props}>{children}</th>;
}

function MarkdownTd({ children, ...props }: any) {
  return <td className="px-6 py-4 whitespace-nowrap" {...props}>{children}</td>;
}

const markdownComponents: Record<string, React.ComponentType<any>> = {
  code: MarkdownCode,
  img: MarkdownImage,
  a: MarkdownLink,
  h1: MarkdownH1,
  h2: MarkdownH2,
  h3: MarkdownH3,
  ul: MarkdownUl,
  ol: MarkdownOl,
  blockquote: MarkdownBlockquote,
  table: MarkdownTable,
  thead: MarkdownTableHead,
  tbody: MarkdownTableBody,
  tr: MarkdownTableRow,
  th: MarkdownTh,
  td: MarkdownTd,
};

const MessageContent: React.FC<MessageContentProps> = ({ content, resolveFileUrl }) => {
  const { t } = useTranslation('common');
  const renderedContent = useMemo(() => {
    if (typeof content === 'object' && content !== null) {
      return (
        <pre className="border border-line dark:border-line-dark bg-white dark:bg-black p-4 rounded-md whitespace-pre-wrap" style={{ overflowWrap: 'anywhere', wordBreak: 'normal' }}>
          <code className="text-sm text-fg  dark:text-fg-dark">{JSON.stringify(content, null, 2)}</code>
        </pre>
        
      );
    }

    const stringContent = content as string;

    const hasFileMarkers = stringContent.includes('](file://');

    if (isJson(stringContent)) {
      return formatJson(stringContent, t('messageContent.invalidJson'));
    } else if (hasFileMarkers || isMarkdown(stringContent)) {
      return (
        <div className="prose prose-sm dark:prose-invert max-w-none whitespace-pre-wrap" style={{ overflowWrap: 'anywhere', wordBreak: 'normal' }}>
          <ReactMarkdown
            components={markdownComponents}
            remarkPlugins={[remarkGfm]}
            urlTransform={(url, key) => markdownUrlTransform(url, key, defaultUrlTransform)}
          >
            {stringContent}
          </ReactMarkdown>
        </div>
      );
    } else {
      return <div className="whitespace-pre-wrap" style={{ overflowWrap: 'anywhere', wordBreak: 'normal' }}>{stringContent}</div>;
    }
  }, [content, t, markdownComponents]);

  return (
    <ResolveFileUrlContext.Provider value={resolveFileUrl}>
      <div className="text-fg dark:text-fg-dark" style={{ overflowWrap: 'anywhere', wordBreak: 'normal' }}>
        {renderedContent}
      </div>
    </ResolveFileUrlContext.Provider>
  );
};

export default React.memo(MessageContent);
