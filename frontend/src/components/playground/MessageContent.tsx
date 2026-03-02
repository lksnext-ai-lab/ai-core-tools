import React from 'react';
import ReactMarkdown from 'react-markdown';
import InlineFileImage from './InlineFileImage';
import InlineFileDownload from './InlineFileDownload';

interface MessageContentProps {
  content: string | object;
  resolveFileUrl?: (fileId: string) => Promise<string>;
}

const IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg']);

function isImageFilename(filename: string): boolean {
  const ext = filename.toLowerCase().lastIndexOf('.');
  return ext !== -1 && IMAGE_EXTENSIONS.has(filename.toLowerCase().slice(ext));
}

const MessageContent: React.FC<MessageContentProps> = ({ content, resolveFileUrl }) => {
  // Check if content is JSON
  const isJson = (str: string) => {
    try {
      JSON.parse(str);
      return true;
    } catch {
      return false;
    }
  };

  // Check if content looks like markdown (has markdown syntax)
  const isMarkdown = (str: string) => {
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
    return markdownPatterns.some(pattern => pattern.test(str));
  };

  // Format JSON for display
  const formatJson = (jsonStr: string) => {
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
  };

  // Custom markdown components including file:// URI handlers
  const markdownComponents: Record<string, React.ComponentType<any>> = {
    code: ({ node, className, children, ...props }: any) => {
      const match = /language-(\w+)/.exec(className || '');
      const isInline = !match;
      return !isInline ? (
        <pre className="bg-gray-100 p-4 rounded-lg overflow-x-auto">
          <code className={className} {...props}>{children}</code>
        </pre>
      ) : (
        <code className="bg-gray-100 px-1 py-0.5 rounded text-sm" {...props}>{children}</code>
      );
    },
    // Images: handle file:// src for agent-generated images
    img: ({ src, alt }: any) => {
      if (!src) return null;
      if (src?.startsWith('file://') && resolveFileUrl) {
        const fileId = src.slice('file://'.length);
        const filename = alt || fileId;
        return (
          <InlineFileImage fileId={fileId} filename={filename} resolveUrl={resolveFileUrl} />
        );
      }
      return <img src={src} alt={alt} className="max-w-full rounded" />;
    },
    // Links: handle file:// href for agent-generated non-image files
    a: ({ node, children, href, ...props }: any) => {
      if (href?.startsWith('file://') && resolveFileUrl) {
        const fileId = href.slice('file://'.length);
        const filename = typeof children === 'string'
          ? children.replace(/^📎\s*/, '').trim()
          : fileId;
        // Markdown images with file:// end up here too when alt text is present
        // but they're handled by the img renderer above. This catches file links.
        if (isImageFilename(filename)) {
          return (
            <InlineFileImage fileId={fileId} filename={filename} resolveUrl={resolveFileUrl} />
          );
        }
        return (
          <InlineFileDownload fileId={fileId} filename={filename} resolveUrl={resolveFileUrl} />
        );
      }
      return (
        <a href={href} className="text-blue-600 hover:text-blue-800 underline"
           target="_blank" rel="noopener noreferrer" {...props}>
          {children}
        </a>
      );
    },
    h1: ({ node, children, ...props }: any) => (
      <h1 className="text-2xl font-bold mb-4 mt-6" {...props}>{children}</h1>
    ),
    h2: ({ node, children, ...props }: any) => (
      <h2 className="text-xl font-bold mb-3 mt-5" {...props}>{children}</h2>
    ),
    h3: ({ node, children, ...props }: any) => (
      <h3 className="text-lg font-bold mb-2 mt-4" {...props}>{children}</h3>
    ),
    ul: ({ node, children, ...props }: any) => (
      <ul className="list-disc list-inside mb-4 space-y-1" {...props}>{children}</ul>
    ),
    ol: ({ node, children, ...props }: any) => (
      <ol className="list-decimal list-inside mb-4 space-y-1" {...props}>{children}</ol>
    ),
    blockquote: ({ node, children, ...props }: any) => (
      <blockquote className="border-l-4 border-gray-300 pl-4 italic text-gray-700 mb-4" {...props}>
        {children}
      </blockquote>
    ),
    table: ({ node, children, ...props }: any) => (
      <div className="overflow-x-auto mb-4">
        <table className="min-w-full border border-gray-300" {...props}>{children}</table>
      </div>
    ),
    th: ({ node, children, ...props }: any) => (
      <th className="border border-gray-300 px-4 py-2 bg-gray-100 font-semibold" {...props}>
        {children}
      </th>
    ),
    td: ({ node, children, ...props }: any) => (
      <td className="border border-gray-300 px-4 py-2" {...props}>{children}</td>
    ),
  };

  // Render content based on type
  const renderContent = () => {
    // Handle object content (already parsed JSON)
    if (typeof content === 'object' && content !== null) {
      return (
        <pre className="bg-gray-100 p-4 rounded-lg overflow-x-auto">
          <code className="text-sm">{JSON.stringify(content, null, 2)}</code>
        </pre>
      );
    }

    const stringContent = content as string;

    // Always use markdown renderer when file:// markers are present
    const hasFileMarkers = stringContent.includes('](file://');

    if (isJson(stringContent)) {
      return formatJson(stringContent);
    } else if (hasFileMarkers || isMarkdown(stringContent)) {
      return (
        <div className="prose prose-sm max-w-none">
          <ReactMarkdown
            components={markdownComponents}
            urlTransform={(url) => url}
          >
            {stringContent}
          </ReactMarkdown>
        </div>
      );
    } else {
      return <div className="whitespace-pre-wrap">{stringContent}</div>;
    }
  };

  return (
    <div className="text-gray-800">
      {renderContent()}
    </div>
  );
};

export default MessageContent;
