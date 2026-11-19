import React, { useState } from 'react';

/**
 * Lightweight, zero-dependency Markdown renderer for AI responses.
 * Supports:
 * - Code blocks with language tag and Copy button (```lang ... ```)
 * - Inline code (`code`)
 * - Bold (**bold** or __bold__)
 * - Italic (*italic* or _italic_)
 * - Headings (###, ##, #)
 * - Unordered bullet lists (- or *)
 * - Ordered numbered lists (1. 2. 3.)
 * - Blockquotes (> quote)
 * - Paragraphs and line breaks
 */

function CodeBlock({ language, code }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Ignore clipboard write failures
    }
  };

  return (
    <div className="md-codeblock">
      <div className="md-codeblock__header">
        <span className="md-codeblock__lang">{language || 'code'}</span>
        <button
          type="button"
          className="md-codeblock__copy-btn"
          onClick={handleCopy}
          aria-label="Copy code block"
        >
          {copied ? '✓ Copied' : 'Copy'}
        </button>
      </div>
      <pre className="md-codeblock__pre">
        <code>{code}</code>
      </pre>
    </div>
  );
}

function parseInline(text) {
  if (!text) return null;

  // Split by inline code, bold, italic
  const tokens = [];
  let remaining = text;
  let keyIndex = 0;

  // Regex to match inline patterns: `code`, **bold**, *italic*
  const pattern = /(`[^`]+`|\*\*[^*]+\*\*|__[^_]+__|\*[^*]+\*|_[^_]+_)/g;
  let lastIndex = 0;
  let match;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      tokens.push(text.substring(lastIndex, match.index));
    }

    const token = match[0];
    if (token.startsWith('`') && token.endsWith('`')) {
      tokens.push(
        <code key={keyIndex++} className="md-inline-code">
          {token.slice(1, -1)}
        </code>
      );
    } else if (
      (token.startsWith('**') && token.endsWith('**')) ||
      (token.startsWith('__') && token.endsWith('__'))
    ) {
      tokens.push(
        <strong key={keyIndex++} className="md-strong">
          {token.slice(2, -2)}
        </strong>
      );
    } else if (
      (token.startsWith('*') && token.endsWith('*')) ||
      (token.startsWith('_') && token.endsWith('_'))
    ) {
      tokens.push(
        <em key={keyIndex++} className="md-em">
          {token.slice(1, -1)}
        </em>
      );
    } else {
      tokens.push(token);
    }

    lastIndex = pattern.lastIndex;
  }

  if (lastIndex < text.length) {
    tokens.push(text.substring(lastIndex));
  }

  return tokens.length > 0 ? tokens : text;
}

export function MarkdownRenderer({ content }) {
  if (!content) return null;

  const lines = content.split('\n');
  const elements = [];
  let index = 0;

  let inCodeBlock = false;
  let codeBlockLang = '';
  let codeBlockBuffer = [];

  let listBuffer = [];
  let listType = null; // 'ul' | 'ol'

  const flushList = () => {
    if (listBuffer.length > 0) {
      if (listType === 'ol') {
        elements.push(
          <ol key={`ol-${index++}`} className="md-ol">
            {listBuffer.map((item, i) => (
              <li key={i}>{parseInline(item)}</li>
            ))}
          </ol>
        );
      } else {
        elements.push(
          <ul key={`ul-${index++}`} className="md-ul">
            {listBuffer.map((item, i) => (
              <li key={i}>{parseInline(item)}</li>
            ))}
          </ul>
        );
      }
      listBuffer = [];
      listType = null;
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Check code fence
    if (line.trim().startsWith('```')) {
      if (!inCodeBlock) {
        flushList();
        inCodeBlock = true;
        codeBlockLang = line.trim().slice(3).trim();
        codeBlockBuffer = [];
      } else {
        inCodeBlock = false;
        elements.push(
          <CodeBlock
            key={`code-${index++}`}
            language={codeBlockLang}
            code={codeBlockBuffer.join('\n')}
          />
        );
        codeBlockBuffer = [];
        codeBlockLang = '';
      }
      continue;
    }

    if (inCodeBlock) {
      codeBlockBuffer.push(line);
      continue;
    }

    // Unordered list (- or *)
    const ulMatch = line.match(/^(\s*)[-*]\s+(.+)$/);
    if (ulMatch) {
      if (listType === 'ol') flushList();
      listType = 'ul';
      listBuffer.push(ulMatch[2]);
      continue;
    }

    // Ordered list (1. 2. etc)
    const olMatch = line.match(/^(\s*)\d+\.\s+(.+)$/);
    if (olMatch) {
      if (listType === 'ul') flushList();
      listType = 'ol';
      listBuffer.push(olMatch[2]);
      continue;
    }

    // If we were inside a list and hit a non-list line, flush it
    if (listBuffer.length > 0) {
      flushList();
    }

    // Headings
    if (line.startsWith('### ')) {
      elements.push(
        <h3 key={`h3-${index++}`} className="md-h3">
          {parseInline(line.slice(4))}
        </h3>
      );
      continue;
    }
    if (line.startsWith('## ')) {
      elements.push(
        <h2 key={`h2-${index++}`} className="md-h2">
          {parseInline(line.slice(3))}
        </h2>
      );
      continue;
    }
    if (line.startsWith('# ')) {
      elements.push(
        <h1 key={`h1-${index++}`} className="md-h1">
          {parseInline(line.slice(2))}
        </h1>
      );
      continue;
    }

    // Blockquote
    if (line.startsWith('> ')) {
      elements.push(
        <blockquote key={`bq-${index++}`} className="md-blockquote">
          {parseInline(line.slice(2))}
        </blockquote>
      );
      continue;
    }

    // Empty line
    if (!line.trim()) {
      continue;
    }

    // Regular paragraph
    elements.push(
      <p key={`p-${index++}`} className="md-p">
        {parseInline(line)}
      </p>
    );
  }

  // Flush any open structures
  if (inCodeBlock) {
    elements.push(
      <CodeBlock
        key={`code-${index++}`}
        language={codeBlockLang}
        code={codeBlockBuffer.join('\n')}
      />
    );
  }
  flushList();

  return <div className="md-body">{elements}</div>;
}
