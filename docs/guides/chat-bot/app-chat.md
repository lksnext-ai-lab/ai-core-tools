# Chat in an App

> Part of [Mattin AI Documentation](../../index.md) · Technical reference: [App Chat](../../ai/app-chat.md)

## What is the Chat?

The **Chat** is a page in every App's menu where you talk directly to a model, without creating an agent. For each message you choose:

- the **Model** that answers,
- an optional **Source** (a knowledge base the answer is grounded on),
- the **Skills** the model may use,
- the **MCP** tools it may call.

Anyone who is a member of the App can use it, including **Viewers**. It is different from the Playground: the Playground tests one agent with the settings an editor gave it; the Chat lets any member pick the ingredients themselves.

## Starting a conversation

1. Open your App and click **Chat** in the menu.
2. Check the selectors above the message box (Model, Source, Skills, MCP).
3. Type a message and press **Enter** (**Shift+Enter** adds a new line), or use the **Send message** button.

Answers stream in as they are generated. While one is being written, the **Stop generating** button stops it. If the page says no model is available, the App has no active AI service: ask an App administrator to configure one (administrators see a **Configure AI services** link).

## Choosing model, source, skills and MCP per message

Whatever is selected when you send a message is used for that message. You can change it at any time, between any two messages of the same conversation.

| Selector | What it does |
|----------|--------------|
| **Model** | The AI service that answers. Models near end of service are flagged; retired ones cannot be selected |
| **Source** | One knowledge source (repository, web domain, SharePoint or silo) searched to answer. **None** disables retrieval |
| **Skills** | Reusable instruction blocks, from the App and from the platform ("System skills") |
| **MCP** | External tool servers configured in the App. The model may call their tools |

Each answer carries a small badge with what produced it (model, and source, skills and MCP if used). Expand it to see the details. If something was deleted later, it is shown as "(deleted)".

### Switching models in the middle of a conversation

You can pick another model, even from another provider, between any two messages and keep talking. The new model receives the conversation so far: your messages, the answers, and the tools that were called with their results. What does **not** carry over is the earlier model's internal reasoning, which only that model can use. Nothing is lost: if you go back to the earlier model, it sees its own earlier answers as it wrote them.

If the conversation is long and the new model has a **smaller context window**, the Chat automatically summarizes the older part before answering and keeps the most recent messages, so the message normally still goes through. This summary replaces the older messages in what the conversation remembers. If even the most recent messages do not fit in the new model, the message fails; switch back to a larger model or use **Reset**.

Some models cannot be used in the Chat at all: a model that cannot call tools fails every message, whatever you selected.

### What the Chat remembers

- A **new** conversation starts with the settings you used last.
- An **opened** conversation keeps its own settings, so going back to an old conversation shows what it was using.
- Your choices are personal. Nobody else sees them.

## Files

Attach files with the **Attach file** button next to the message box, as in the Playground. They belong to the conversation you attached them in and stay available to later messages of that conversation. Files of a type the Chat cannot read are ignored, as in the Playground.

**Indexed or sent whole.** If an administrator set a **Default embedding service** in the App settings, the files you attach are indexed into a temporary knowledge base of that conversation and the model searches them for what is relevant to each question. If none is set (or it has reached end of service), the files are sent whole to the model with your message. In that case the Chat page shows the notice "Attached files will not be indexed": administrators get an **Open App settings** link, other members are asked to contact an administrator or owner. Whole files can be too large for a model's context window; if a long document fails, ask an administrator to set the default embedding service. If indexing takes too long (about a minute) or the provider fails, the file stays attached and is sent whole.

Images that an answer shows from the conversation's files are fetched when the message appears and **can stop loading after five minutes**; reopen the conversation to reload them. File download buttons always get a fresh link when you click them.

Images are sent to the model you selected. The Chat does not check whether that model understands images, so pick a model with vision when you attach one. Once an image is attached to a conversation it is sent again with every later message, so if you switch to a model without vision, those messages fail. Continue in a new conversation (or use a model with vision).

## Running code

If an administrator has turned on **Allow running code in the Chat** in the App settings, the model can run code in a private sandbox to answer you, and skills that include scripts can run them. Nothing changes in how you use the Chat: the code runs when the model decides it needs to, and files it creates appear with the answer like any other file.

- **One sandbox per conversation.** It is created the first time the model runs code, belongs to that conversation only (the platform never shares it; with a self-hosted OpenSandbox server, however, other members' code can reach it, see [For administrators](#for-administrators)), and is removed when you reset or delete the conversation or your user is deleted.
- **It does not last.** An idle sandbox is removed after about two minutes. Working files and any packages installed in it are lost; only result files already pulled into the message's output folder stay. A new sandbox only gets the files you attached in the current message, so attach them again if the model needs them.
- **Limits per message.** The model can run code at most 5 times per message (the Python tool and shell commands share this count), a shell command is cut off after 60 seconds and shell commands cannot run in the background. A skill whose instructions need a longer shell step cannot finish it in the Chat; use an agent for those.
- **Limits per person.** You can have 3 live sandboxes at once and the App 10. If you are over the limit the Chat first removes your own sandbox that has been idle the longest (idle for at least a minute). If none qualifies, the code tool returns a capacity error: wait a moment and send the message again. Other members' sandboxes are never removed to make room for yours, so when the App's 10 are in use by others you may have to wait.
- **Result files.** At most 20 files per message, 50 MB each and 100 MB in total, delivered within about 20 seconds. Files that do not fit are skipped and the Chat shows "N files created by the code could not be delivered (size, number or time limit)". The answer text is not changed.
- **No approval.** Code runs without asking you: the Chat cannot ask for approval.

If the App does not allow it, skills with scripts still load but their scripts do not run, and the Chat page shows a notice once you select a skill. If instead the App's sandbox service has reached end of service, or its provider is not allowed on this installation, the notice is shown whether or not a skill is selected.

## Managing conversations

- The **Conversations** list shows yours, newest first. **New** starts another conversation; the **Rename conversation** and **Delete conversation** buttons on each entry rename or delete it (deleting asks for confirmation).
- **Reset** (in the chat toolbar) forgets the conversation's history but keeps its settings.
- If you switch to another conversation while an answer is being written, the answer is still completed and is there when you come back.
- A conversation answers **one message at a time**. If you send another while the previous one is still being answered (for example from a second tab), the message is not sent and your text stays in the message box; wait for the answer to finish and send it again.
- Deleting or resetting a conversation also removes its attached files and their temporary knowledge base. If your user account is deleted, so are your Chat conversations and files.
- **Leaving an App, or being removed from it, deletes your Chat conversations and files in that App.** The leave confirmation does not mention this, so export anything you need before you leave. Your Chat data in other Apps, and other members' data, are not touched. The owner cannot leave their own App.
- **Reset asks for confirmation** before it forgets the history.
- If a long task uses up the steps the assistant is allowed to take, the message ends with "The assistant ran out of steps before finishing". Your conversation and the files created so far are kept: write "continue" and it carries on. At most 10 files can be sent with one message (the default; the platform operator can change it). Beyond that the Chat shows "Too many files in one message. Send fewer files at a time.", your typed text goes back to the message box and the files stay attached.

## Using the Chat with a keyboard or a screen reader

- **Esc** stops a running answer. When you send a message, keyboard focus moves to **Stop generating**; when the answer ends, focus returns to the message box (unless you moved it elsewhere on purpose).
- A screen reader hears one short status when the assistant starts answering and one when the answer is ready (or failed, or the conversation was reset). The text being streamed is **not** read out while it is written; read the answer once it is complete. Each message is prefixed with who wrote it.
- The **Conversations** panel behaves as a modal dialog: focus moves into it, the rest of the page is inert, Tab stays inside it, Esc closes it and focus goes back to the button that opened it.
- Animations are reduced when your system asks for reduced motion.

## Privacy

What the Chat does guarantee: **your conversations are private to you at the database and API level.** Other members of the App, including administrators, owners and platform administrators using the Chat, cannot read, list or delete your Chat conversations or files through the platform. Chat conversations never appear in the Agents list, in the Marketplace, in exports, or through the public API, MCP or A2A.

What it does **not** guarantee: it is not a technical protection against the people who run the App or the platform. App administrators and platform operators decide which AI-service and embedding endpoints, MCP server URLs and skills the Chat can use, and which LangSmith project traces it, so they can point them at services that receive your content. In `LOCAL` sign-in mode, platform administrators can also set a user's password through the admin set-password flow. Treat the Chat as a normal work tool, not a confidential channel from your administrators.

Where your content can go:

- **The model providers** of the AI services you select.
- **The embedding provider**, if the App has a **Default embedding service**: the files you attach are sent to it (it can be a platform-wide service) and their text chunks are stored in the App's vector database until the conversation is reset or deleted.
- **MCP servers** you select. When you select an MCP server that connects by URL, your sign-in token is sent to it so it can identify you, as in the Playground. Only select servers you trust.
- **LangSmith**, if the App has tracing enabled: your Chat messages are sent to the App's LangSmith project, like those of any agent. Only the App owner can change the App's LangSmith key; the platform operator can also configure a global fallback.
- **The sandbox provider**, if the App allows [running code](#running-code): the code the model writes and the files you attach in that message run in a sandbox of the App's sandbox provider (or the platform's system default one). With a self-hosted OpenSandbox server, other members' code can reach your sandbox (see [For administrators](#for-administrators)).
- **Image links.** When your images are sent to the model as links, those links do not expire and every provider the conversation used keeps them. Deleting or resetting the conversation, or removing you from the App, deletes the file and so makes the links useless.

When something fails, the platform's failure logs and the metrics dashboard record only the kind of error and an identifier, not what you wrote or the provider's error text. This covers failure logs and metrics only: other log lines on success can contain file names.

## Warnings and messages

| Message | What it means |
|---------|---------------|
| "Part of your selection was not used" | Something you had selected (model, source or skill) was removed or retired since. It was dropped from the selection; check the selectors and choose again |
| "An MCP configuration could not be used (unavailable or removed); the message was answered without it" | A selected MCP server could not be reached. The tools of **all** selected MCP configs are unavailable for that message, not just the failing one. Try again later or deselect it |
| "The selected model has reached end of service" | The model is retired. Choose another and send the message again |
| "That conversation is not available. A new one is open." | The link points to a conversation that does not exist or is not yours |
| "You cannot send messages in this App right now" | The App may be frozen after a plan downgrade, or your access changed. Ask an App administrator |
| "This conversation is still answering a previous message. Wait for it to finish and try again. Your message was kept in the box." | Another message of the same conversation is still being answered (another tab, or a retry). Wait and send again. If it never finishes after a server restart, it frees itself after about 11 minutes |
| "Attached files will not be indexed" | The App has no usable default embedding service; files are sent whole. See [Files](#files) |
| "Sending is disabled: ..." | There is no usable model, or none selected. Select one |
| "Code cannot be run in this chat" | Skills with scripts load, but their scripts will not run: running code is turned off for the App (shown only once a skill is selected), its sandbox service has reached end of service, or its provider is not allowed on this installation. See [Running code](#running-code) |
| "N files created by the code could not be delivered (size, number or time limit)" | Some result files were over the limits and were skipped. The answer itself is complete |
| "The assistant ran out of steps before finishing. Your conversation and any files created so far were kept: write "continue" to let it carry on." | The message used up the steps the assistant may take. Nothing is lost: write "continue" |

## What the Chat does not do

- **No approvals.** Agents in the Agents area can be set to ask a human before using certain tools, and to filter personal data. These rules do not apply in the Chat. If a tool would require approval (for example from an MCP server), the Chat cannot ask you: the tool is **not run** and the model is told it was refused. Use an agent for those workflows.
- No structured output or agent tools: those belong to agents. Running code is available only when the App's administrator allows it (see [Running code](#running-code)).

## For administrators

- The Chat needs at least one active AI service in the App (or a system one). Add a source, skills or MCP configs in the App to make them selectable.
- **Default embedding service.** In the App settings, set **Default embedding service** (next to the default sandbox) so Chat attachments are indexed and retrieved by relevance instead of being sent whole. Without it, or if the chosen service is retired, attachments are sent whole and members see a notice. Everyone's attachments then go to that embedding provider and are stored in the App's vector database until the conversation is reset or deleted. The service shows up in its **Used by** view and in end-of-service warnings. A conversation keeps the service its temporary knowledge base was created with, even if you change the default later.
- **Allow running code in the Chat** (App settings, off by default; administrators and the owner can change it, other roles see it read-only). Turning it on lets **every member of the App, Viewers included**, run code in a sandbox from the Chat. It uses the App's **default sandbox service**. If the App has none, it uses the **platform's system default** sandbox provider. A default sandbox service that has reached end of service switches the feature off for the Chat, with no fallback to the system default. Read these before turning it on:
  - With a self-hosted **OpenSandbox** server, sandboxes are **not isolated from each other**: code run by one member can reach other members' sandboxes on the same server, even across Apps. Whether E2B and Daytona isolate sandboxes from each other has not been verified by this project.
  - Outbound network from the sandboxes is on by default with the bundled OpenSandbox setup (internet, services on the Docker host, the local network) unless the platform operator uses the hardened override (no network; `pip install` stops working).
  - With no App default sandbox service, the system default sandbox provider's credentials are used and its usage is charged to the platform (for a self-hosted OpenSandbox: the host's capacity), for any App whose administrator turns this on.
  - The Chat **cannot ask for approval** before running code.
  - A member can still exhaust the backend's memory (a sandbox with a huge number of files, or a command that prints without end) or fill the sandbox host's disk. This is a known, accepted risk, tracked as a follow-up.
  - The limits on live sandboxes (3 per user, 10 per App) are counted per backend process, not across all workers. The 5 executions per message and the result-file limits apply per message.
  - If the system default is not running (for example the OpenSandbox profile is not started), the Chat does not show a warning: the model still gets the code tools, the first call returns an error and the answer is written without code. The App's default sandbox service shows up in **Used by** and in end-of-service warnings. See [Knowledge Base AI Services](kb-ai-services.md#service-end-of-service).
- **Choose trusted sources, MCP servers and skills.** In every Chat the model has a tool that downloads a URL into its working directory, with no approval step. A malicious instruction hidden in a document, an MCP result, an uploaded file or a skill (a prompt injection) can make the model send conversation text to a public web address. This is a known and accepted risk; the only mitigation is to make selectable only sources, MCP servers and skills you trust. See [App Chat](../../ai/app-chat.md#accepted-risks-of-the-chat-in-addition-to-the-sandbox-ones).
- **Privacy limits.** Members' conversations are private from other members and administrators through the platform, but you (and the platform operator) control the AI, embedding and MCP endpoints and the LangSmith project that receive their content. Do not describe the Chat to members as confidential from administrators.
- **Removing a member** from the App deletes that member's Chat conversations and files in the App (the same when they leave). The removal confirmation in the interface does not say so.
- **App settings permissions.** Administrators and the owner can save the App settings. Only the owner can change or clear the LangSmith key (it is read-only for administrators). Deleting the App, transferring ownership and managing collaborators are unchanged.
- Temporary knowledge bases of conversations do not appear in the silo, repository or output-parser lists and do not count against the plan's silo limit.
- Models, sources and skills appear in the selector according to what exists in the App. A frozen App (after a plan downgrade) accepts no new Chat messages or uploads; existing conversations can still be read and deleted.
- Chat usage appears in the metrics dashboards under the **INTERNAL_CHAT** channel.

## Known limits

- Rare case: if the server stops while it is rejecting a tool approval, a conversation that uses a provider other than OpenAI may fail on every message until you **Reset** it.
- There is no warning before sending images to a model without vision, and once an image is attached it goes with every later message of that conversation, so switching to a model without vision makes those messages fail.
- A model that cannot call tools fails every message in the Chat.
- Code in the Chat was only tested with simulated sandbox providers, not against a real OpenSandbox, Daytona or E2B.
- Resetting or deleting a conversation destroys its sandbox only when the same server process holds it; with several workers, other sandboxes expire on their own (the provider's time limit).
- If the most recent messages alone are larger than a small model's context window, the message still fails. Models whose size the platform does not know (for example Ollama and Azure AI models) are assumed to have a window of about 37,600 tokens, with summarization starting at 32,000, even if their real window is smaller.
- When a long conversation is summarized and the answer then fails, the older messages are already replaced by the summary.
- With a platform base URL configured, images are sent as links, which an Ollama ("Custom") model probably cannot read.
- In the history, your own message that had an image can show a raw `[IMAGE:...]` marker instead of the picture.
- These behaviours were tested with simulated providers, not against the real provider APIs, so a provider can still reject a conversation that switched models for reasons the tests cannot show.
- After a server crash in the middle of an answer, that conversation can answer "still answering" for several minutes. Right after a stream is cut there can also be a brief window in which the previous message has not fully stopped.
- Files sent whole (no default embedding service) can exceed a model's context window.

See also: [Conversations and the Playground](kb-conversations.md) · [Skills](kb-skills.md) · [Silos and RAG](kb-silos-and-rag.md) · [MCP](kb-mcp.md)
