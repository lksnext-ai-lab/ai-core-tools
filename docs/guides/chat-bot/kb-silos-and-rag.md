# Silos, Repositories, Domains, and RAG

## What is a Silo?

A **Silo** is a knowledge base. It stores documents and web content as vector embeddings so that agents can search it semantically — finding relevant information even when the user's question doesn't match exact keywords.

When an agent has a linked Silo, it automatically retrieves relevant content from the Silo before answering. This technique is called **RAG** (Retrieval-Augmented Generation).

## Creating a Silo

1. Open your App and go to **Silos**.
2. Click **New Silo**.
3. Give it a name (e.g. "Product Documentation").
4. Select an **Embedding Service** — this determines how documents are vectorized.
5. Save.

The Silo is now empty. You need to populate it with content via Repositories or Domains.

## Repositories — Uploading Files

A **Repository** is a collection of uploaded files inside a Silo.

**To add a Repository:**
1. Open a Silo and click **New Repository**.
2. Give it a name.
3. Upload files — supported formats: PDF, Word, TXT, Markdown, images (with OCR), and audio (transcribed).

Uploaded files are automatically processed and indexed into the Silo's vector store. Large documents are chunked automatically.

**Supported file types:**

| Type | Processing |
|------|-----------|
| PDF | Text extraction (or OCR if scanned) |
| DOCX, TXT, MD | Direct text extraction |
| Images (PNG, JPG) | OCR via vision model |
| Audio (MP3, WAV) | Transcription via Whisper |

## Domains — Web Crawling

A **Domain** is a web source whose pages are crawled and indexed into a Silo.

**To add a Domain:**
1. Open a Silo and click **New Domain**.
2. Enter the base URL (e.g. `https://docs.yourcompany.com`).
3. Configure the crawl depth and any URL filters.
4. Start the crawl.

Pages discovered during the crawl are vectorized and stored in the Silo. You can re-crawl a Domain to pick up updated content.

## Linking a Silo to an Agent

1. Open the agent configuration.
2. Set the **Silo** field to the Silo you want the agent to search.
3. Save.

The agent will now automatically search the Silo for relevant content when answering questions.

## RAG in Practice

When a user sends a message to an agent with a linked Silo:

1. The platform searches the Silo for document chunks semantically similar to the user's message.
2. The relevant chunks are injected into the agent's context alongside the user's message.
3. The agent uses that context to give a grounded, accurate answer.

The agent can tell the user which document a piece of information came from if the system prompt instructs it to do so.

## Tips

- **Keep documents clean**: Remove headers/footers, page numbers, and boilerplate before uploading for better retrieval quality.
- **Chunk size matters**: Very long documents may need to be split manually if retrieval quality is poor.
- **Re-index after updates**: If you update a document, delete the old version and re-upload to refresh the index.
- **Test retrieval**: Use the agent's Playground to ask questions and check whether it retrieves the right content.
