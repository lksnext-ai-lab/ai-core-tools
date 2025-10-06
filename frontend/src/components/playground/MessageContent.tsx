import React from 'react';
import ReactMarkdown from 'react-markdown';

interface MessageContentProps {
  content: string | object;
}

const MessageContent: React.FC<MessageContentProps> = ({ content }) => {
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

  // Render content based on type
  const renderContent = () => {
    // Handle object content (already parsed JSON)
    if (typeof content === 'object' && content !== null) {
      return (
        <pre className="bg-gray-100 p-4 rounded-lg overflow-x-auto">
          <code className="text-sm">
            {JSON.stringify(content, null, 2)}
          </code>
        </pre>
      );
    }
    
    // Handle string content
    const stringContent = content as string;
    if (isJson(stringContent)) {
      return formatJson(stringContent);
    } else if (isMarkdown(stringContent)) {
      return (
        <div className="prose prose-sm max-w-none">
                      <ReactMarkdown
              components={{
              // Customize code blocks
              code: ({ node, className, children, ...props }: any) => {
                const match = /language-(\w+)/.exec(className || '');
                const isInline = !match;
                return !isInline ? (
                  <pre className="bg-gray-100 p-4 rounded-lg overflow-x-auto">
                    <code className={className} {...props}>
                      {children}
                    </code>
                  </pre>
                ) : (
                  <code className="bg-gray-100 px-1 py-0.5 rounded text-sm" {...props}>
                    {children}
                  </code>
                );
              },
              // Customize links
              a: ({ node, children, href, ...props }) => (
                <a 
                  href={href} 
                  className="text-blue-600 hover:text-blue-800 underline"
                  target="_blank"
                  rel="noopener noreferrer"
                  {...props}
                >
                  {children}
                </a>
              ),
              // Customize headers
              h1: ({ node, children, ...props }) => (
                <h1 className="text-2xl font-bold mb-4 mt-6" {...props}>
                  {children}
                </h1>
              ),
              h2: ({ node, children, ...props }) => (
                <h2 className="text-xl font-bold mb-3 mt-5" {...props}>
                  {children}
                </h2>
              ),
              h3: ({ node, children, ...props }) => (
                <h3 className="text-lg font-bold mb-2 mt-4" {...props}>
                  {children}
                </h3>
              ),
              // Customize lists
              ul: ({ node, children, ...props }) => (
                <ul className="list-disc list-inside mb-4 space-y-1" {...props}>
                  {children}
                </ul>
              ),
              ol: ({ node, children, ...props }) => (
                <ol className="list-decimal list-inside mb-4 space-y-1" {...props}>
                  {children}
                </ol>
              ),
              // Customize blockquotes
              blockquote: ({ node, children, ...props }) => (
                <blockquote className="border-l-4 border-gray-300 pl-4 italic text-gray-700 mb-4" {...props}>
                  {children}
                </blockquote>
              ),
              // Customize tables
              table: ({ node, children, ...props }) => (
                <div className="overflow-x-auto mb-4">
                  <table className="min-w-full border border-gray-300" {...props}>
                    {children}
                  </table>
                </div>
              ),
              th: ({ node, children, ...props }) => (
                <th className="border border-gray-300 px-4 py-2 bg-gray-100 font-semibold" {...props}>
                  {children}
                </th>
              ),
              td: ({ node, children, ...props }) => (
                <td className="border border-gray-300 px-4 py-2" {...props}>
                  {children}
                </td>
              ),
                          }}
            >
              {stringContent}
            </ReactMarkdown>
        </div>
      );
    } else {
      // Plain text - preserve line breaks
      return (
        <div className="whitespace-pre-wrap">
          {stringContent}
        </div>
      );
    }
  };

  return (
    <div className="text-gray-800">
      {renderContent()}
    </div>
  );
};

export default MessageContent; 