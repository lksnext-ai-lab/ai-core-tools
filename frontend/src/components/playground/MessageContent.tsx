import React, { createContext, useContext, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import InlineFileImage from './InlineFileImage';
import InlineFileDownload from './InlineFileDownload';

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

function formatJson(jsonStr: string): React.ReactNode {
  try {
    const parsed = JSON.parse(jsonStr);
    return (
      <pre className="bg-gray-100 p-4 rounded-lg overflow-x-auto">
        <code className="text-sm">
          {JSON.stringify(parsed, null, 2)}
        </code>
      </pre>
    );
  } catch {
    return <span className="text-red-500">Invalid JSON</span>;
  }
}

function MarkdownCode({ className, children, ...props }: any) {
  const match = /language-(\w+)/.exec(className || '');
  const isInline = !match;
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    const text = typeof children === 'string' ? children : String(children);
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return isInline ? (
    <code className="bg-gray-100 px-1 py-0.5 rounded text-sm" {...props}>{children}</code>
  ) : (
    <div className="relative group">
      <button
        onClick={handleCopy}
        aria-label="Copy code"
        className="absolute top-2 right-2 p-1.5 rounded-md bg-gray-700/50 hover:bg-gray-700 text-gray-300 hover:text-white transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100"
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
      <pre className="bg-gray-900 dark:bg-gray-950 text-gray-100 p-4 pr-12 rounded-lg overflow-x-auto">
        <code className={className} {...props}>{children}</code>
      </pre>
    </div>
  );
}

function MarkdownImage({ src, alt }: any) {
  const resolveFileUrl = useContext(ResolveFileUrlContext);
  if (!src) return null;
  if (src?.startsWith('file://') && resolveFileUrl) {
    const fileId = src.slice('file://'.length);
    const filename = alt || fileId;
    return <InlineFileImage fileId={fileId} filename={filename} resolveUrl={resolveFileUrl} />;
  }
  return <img src={src} alt={alt} className="max-w-full rounded" />;
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
    <a href={href} className="text-blue-600 hover:text-blue-800 underline"
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
    <blockquote className="border-l-4 border-gray-300 pl-4 italic text-gray-700 mb-4" {...props}>
      {children}
    </blockquote>
  );
}

function MarkdownTable({ children, ...props }: any) {
  return (
    <div className="overflow-x-auto mb-4 rounded-lg overflow-hidden">
      <table className="min-w-full border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden" {...props}>{children}</table>
    </div>
  );
}

function MarkdownTh({ children, ...props }: any) {
  return <th className="border border-gray-200 dark:border-gray-700 px-4 py-2 bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 font-semibold" {...props}>{children}</th>;
}

function MarkdownTd({ children, ...props }: any) {
  return <td className="border border-gray-200 dark:border-gray-700 px-4 py-2" {...props}>{children}</td>;
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
  th: MarkdownTh,
  td: MarkdownTd,
};

const MessageContent: React.FC<MessageContentProps> = ({ content, resolveFileUrl }) => {
  const renderedContent = useMemo(() => {
    if (typeof content === 'object' && content !== null) {
      return (
        <pre className="bg-gray-100 p-4 rounded-lg overflow-x-auto">
          <code className="text-sm">{JSON.stringify(content, null, 2)}</code>
        </pre>
      );
    }

    const stringContent = content;

    const hasFileMarkers = stringContent.includes('](file://');

    if (isJson(stringContent)) {
      return formatJson(stringContent);
    } else if (hasFileMarkers || isMarkdown(stringContent)) {
      return (
        <div className="prose prose-sm dark:prose-invert max-w-none">
          <ReactMarkdown
            components={markdownComponents}
            remarkPlugins={[remarkGfm]}
            urlTransform={(url) => url}
          >
            {stringContent}
          </ReactMarkdown>
        </div>
      );
    } else {
      return <div className="whitespace-pre-wrap">{stringContent}</div>;
    }
  }, [content, markdownComponents]);

  return (
    <ResolveFileUrlContext.Provider value={resolveFileUrl}>
      <div className="text-gray-800 dark:text-gray-200">
        {renderedContent}
      </div>
    </ResolveFileUrlContext.Provider>
  );
};

export default React.memo(MessageContent);
