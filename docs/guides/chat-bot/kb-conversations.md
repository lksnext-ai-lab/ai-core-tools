# Conversations and the Playground

## What is the Playground?

The **Playground** is the chat interface where you interact with an agent. Each Playground session is a **Conversation** — a persistent chat thread with its own history.

## Starting a Conversation

1. Open your App and go to **Agents**.
2. Click on an agent to open it.
3. Click **Open Playground** (or the chat icon).
4. Type a message and press **Enter** or click **Send**.

## Conversation History

Conversations are saved automatically. You can:
- Return to a previous conversation and continue where you left off.
- Browse all your conversations for a specific agent.
- Delete conversations you no longer need.

## File Attachments

You can attach files to messages in the Playground. The agent will process the file and use its content to answer your question.

**Supported file types:**

| Type | How the agent uses it |
|------|----------------------|
| PDF | Extracts and reads the text |
| Images (PNG, JPG) | Reads text via OCR, or analyzes the image directly (if the LLM is multimodal) |
| Audio (MP3, WAV) | Transcribes the audio to text |
| TXT, MD | Reads the content directly |

**How to attach a file:**
1. Click the attachment icon (paperclip) in the chat input area.
2. Select the file from your device.
3. Type your message and send.

## Streaming Responses

Responses appear word by word as the LLM generates them (streaming). You can stop a response mid-stream by clicking **Stop**.

## Clearing Memory

If the agent is configured with memory, it remembers previous messages in the conversation. To start a fresh session:
- Click **New Conversation** to create a new thread. The old conversation is preserved in history.

## The Platform Chatbot

The floating chat button in the bottom-right corner of the platform (if enabled by your administrator) is the **Platform Chatbot** — a special agent available on every page. It works just like the Playground but is always accessible. Your conversation with it persists across page navigations. Click **New conversation** in its header to start fresh.
