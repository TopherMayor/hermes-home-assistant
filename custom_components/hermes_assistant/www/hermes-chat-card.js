/**
 * Hermes Chat Card for Home Assistant Lovelace.
 *
 * A chat card that connects to the Hermes gateway API server
 * and provides a full conversation interface with typing indicators,
 * message history, and voice message support.
 *
 * Installation:
 * 1. Copy this file to www/hermes-chat-card.js in your HA config
 * 2. Add to Lovelace via "Add Card" → "Manual Card" → type: custom:hermes-chat-card
 * 3. Or use the "Resources" panel to add as a JavaScript module
 *
 * Configuration options:
 *   gateway_url   - Hermes API server URL (default: http://localhost:8642)
 *   api_key       - API key for authentication (or set HERMES_API_KEY env)
 *   title         - Card title (default: "Hermes")
 *   prominent    - Show header bar (default: true)
 *   hide_header   - Hide the header entirely (default: false)
 *   user_name     - Name for user messages (default: "You")
 *   user_color    - Accent color for user messages (default: "#818cf8")
 *   assistant_name - Name for assistant messages (default: "Hermes")
 *   assistant_color - Accent color for assistant messages (default: "#34d399")
 *   placeholder   - Input placeholder text (default: "Ask Hermes anything…")
 *   max_history   - Max messages to show (default: 50, max: 200)
 *   disable_paste - Prevent image paste (default: false)
 */

class HermesChatCard extends HTMLElement {
  constructor() {
    super();
    this._conversationId = this._uuidv4();
    this._messages = [];
    this._historyMax = 50;
    this._streamBuffer = "";
    this._isStreaming = false;
    this._abortController = null;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._initialized) {
      this._initialize();
    }
  }

  _initialize() {
    this._gatewayUrl = this._config.gateway_url || "http://localhost:8642";
    this._apiKey = this._config.api_key || "";
    this._historyMax = Math.min(this._config.max_history || 50, 200);

    this._render();
    this._loadHistory();
    this._setupResizeObserver();

    this._chatContainer = this.shadowRoot.querySelector(".chat-messages");
    this._inputField = this.shadowRoot.querySelector(".chat-input textarea");
    this._sendBtn = this.shadowRoot.querySelector(".chat-send-btn");

    this._inputField.addEventListener("keydown", (e) => this._handleKeyDown(e));
    this._sendBtn.addEventListener("click", () => this._handleSend());

    this._initialized = true;
  }

  _configSchema() {
    return {
      gateway_url: { type: "string", default: "http://localhost:8642" },
      api_key: { type: "string", default: "" },
      title: { type: "string", default: "Hermes" },
      prominent: { type: "boolean", default: true },
      hide_header: { type: "boolean", default: false },
      user_name: { type: "string", default: "You" },
      user_color: { type: "string", default: "#818cf8" },
      assistant_name: { type: "string", default: "Hermes" },
      assistant_color: { type: "string", default: "#34d399" },
      placeholder: { type: "string", default: "Ask Hermes anything…" },
      max_history: { type: "number", default: 50 },
      disable_paste: { type: "boolean", default: false },
    };
  }

  setConfig(config) {
    // Validate config
    const schema = this._configSchema();
    for (const [key, def] of Object.entries(schema)) {
      if (config[key] === undefined) {
        config[key] = def.default;
      }
    }
    this._config = config;
  }

  getConfigEl() {
    return this._config;
  }

  _render() {
    const c = this._config || {};
    const hideHeader = c.hide_header;
    const prominent = c.prominent !== false && !hideHeader;
    const title = c.title || "Hermes";
    const userColor = c.user_color || "#818cf8";
    const assistantColor = c.assistant_color || "#34d399";
    const userName = c.user_name || "You";
    const assistantName = c.assistant_name || "Hermes";
    const placeholder = c.placeholder || "Ask Hermes anything…";

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: flex;
          flex-direction: column;
          height: 500px;
          max-height: 100%;
          background: var(--lovelace-card-background, #1a1a2e);
          border-radius: 16px;
          overflow: hidden;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          box-shadow: 0 4px 24px rgba(0,0,0,0.4);
        }

        /* Header */
        .chat-header {
          display: ${hideHeader ? "none" : "flex"};
          align-items: center;
          gap: 12px;
          padding: 16px 20px;
          background: ${prominent
            ? "linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)"
            : "transparent"};
          border-bottom: 1px solid rgba(255,255,255,0.06);
        }
        .chat-header-avatar {
          width: 36px;
          height: 36px;
          border-radius: 50%;
          background: linear-gradient(135deg, #34d399, #059669);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 18px;
          flex-shrink: 0;
        }
        .chat-header-info { flex: 1; }
        .chat-header-title {
          font-size: 16px;
          font-weight: 600;
          color: #fff;
        }
        .chat-header-subtitle {
          font-size: 11px;
          color: rgba(255,255,255,0.4);
          margin-top: 1px;
        }
        .chat-header-actions { display: flex; gap: 4px; }
        .header-btn {
          width: 32px;
          height: 32px;
          border: none;
          background: rgba(255,255,255,0.06);
          border-radius: 8px;
          color: rgba(255,255,255,0.5);
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 14px;
          transition: all 0.15s;
        }
        .header-btn:hover { background: rgba(255,255,255,0.1); color: #fff; }

        /* Messages */
        .chat-messages {
          flex: 1;
          overflow-y: auto;
          padding: 16px 20px;
          display: flex;
          flex-direction: column;
          gap: 12px;
          scroll-behavior: smooth;
        }
        .chat-messages::-webkit-scrollbar { width: 6px; }
        .chat-messages::-webkit-scrollbar-track { background: transparent; }
        .chat-messages::-webkit-scrollbar-thumb {
          background: rgba(255,255,255,0.1);
          border-radius: 3px;
        }

        /* Message bubbles */
        .message {
          display: flex;
          flex-direction: column;
          max-width: 82%;
          animation: msgIn 0.2s ease-out;
        }
        @keyframes msgIn {
          from { opacity: 0; transform: translateY(6px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .message.user { align-self: flex-end; align-items: flex-end; }
        .message.assistant { align-self: flex-start; align-items: flex-start; }

        .message-role {
          font-size: 11px;
          font-weight: 600;
          margin-bottom: 4px;
          padding: 0 4px;
        }
        .message.user .message-role { color: ${userColor}; }
        .message.assistant .message-role { color: ${assistantColor}; }

        .message-bubble {
          padding: 10px 14px;
          border-radius: 14px;
          font-size: 14px;
          line-height: 1.5;
          word-break: break-word;
          white-space: pre-wrap;
        }
        .message.user .message-bubble {
          background: ${userColor};
          color: #fff;
          border-bottom-right-radius: 4px;
        }
        .message.assistant .message-bubble {
          background: rgba(255,255,255,0.08);
          color: rgba(255,255,255,0.9);
          border-bottom-left-radius: 4px;
        }

        /* Typing indicator */
        .typing-indicator {
          display: none;
          align-self: flex-start;
          padding: 4px 0;
        }
        .typing-indicator.visible { display: flex; align-items: center; gap: 8px; }
        .typing-dots {
          display: flex;
          gap: 4px;
          padding: 12px 16px;
          background: rgba(255,255,255,0.08);
          border-radius: 14px;
          border-bottom-left-radius: 4px;
        }
        .typing-dot {
          width: 6px;
          height: 6px;
          background: rgba(255,255,255,0.5);
          border-radius: 50%;
          animation: typingBounce 1.4s infinite ease-in-out;
        }
        .typing-dot:nth-child(2) { animation-delay: 0.2s; }
        .typing-dot:nth-child(3) { animation-delay: 0.4s; }
        @keyframes typingBounce {
          0%, 80%, 100% { transform: scale(0.8); opacity: 0.5; }
          40% { transform: scale(1); opacity: 1; }
        }

        /* Input area */
        .chat-input {
          display: flex;
          align-items: flex-end;
          gap: 8px;
          padding: 12px 16px;
          background: rgba(0,0,0,0.2);
          border-top: 1px solid rgba(255,255,255,0.06);
        }
        .chat-input textarea {
          flex: 1;
          background: rgba(255,255,255,0.06);
          border: 1px solid rgba(255,255,255,0.08);
          border-radius: 12px;
          color: #fff;
          font-size: 14px;
          padding: 10px 14px;
          resize: none;
          min-height: 44px;
          max-height: 120px;
          font-family: inherit;
          outline: none;
          transition: border-color 0.15s;
          line-height: 1.4;
        }
        .chat-input textarea::placeholder { color: rgba(255,255,255,0.3); }
        .chat-input textarea:focus { border-color: ${assistantColor}; }
        .chat-send-btn {
          width: 44px;
          height: 44px;
          border: none;
          border-radius: 12px;
          background: ${assistantColor};
          color: #fff;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 18px;
          flex-shrink: 0;
          transition: all 0.15s;
        }
        .chat-send-btn:hover { filter: brightness(1.1); transform: scale(1.05); }
        .chat-send-btn:active { transform: scale(0.95); }
        .chat-send-btn:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }

        /* Error banner */
        .error-banner {
          display: none;
          padding: 10px 16px;
          background: rgba(239, 68, 68, 0.2);
          border-top: 1px solid rgba(239, 68, 68, 0.3);
          color: #fca5a5;
          font-size: 13px;
          text-align: center;
        }
        .error-banner.visible { display: block; }

        /* Empty state */
        .empty-state {
          flex: 1;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 12px;
          color: rgba(255,255,255,0.3);
          padding: 40px 20px;
          text-align: center;
        }
        .empty-state-icon { font-size: 48px; opacity: 0.5; }
        .empty-state-text { font-size: 14px; max-width: 260px; line-height: 1.5; }
      </style>

      <div class="chat-header">
        <div class="chat-header-avatar">🤖</div>
        <div class="chat-header-info">
          <div class="chat-header-title">${title}</div>
          <div class="chat-header-subtitle">Powered by Hermes Agent</div>
        </div>
        <div class="chat-header-actions">
          <button class="header-btn" id="btn-clear" title="Clear conversation">🗑️</button>
        </div>
      </div>

      <div class="chat-messages" id="messages">
        <div class="empty-state" id="empty-state">
          <div class="empty-state-icon">💬</div>
          <div class="empty-state-text">
            Ask Hermes anything — from controlling your smart home to answering questions about your Home Assistant setup.
          </div>
        </div>
      </div>

      <div class="typing-indicator" id="typing-indicator">
        <div class="typing-dots">
          <div class="typing-dot"></div>
          <div class="typing-dot"></div>
          <div class="typing-dot"></div>
        </div>
      </div>

      <div class="error-banner" id="error-banner"></div>

      <div class="chat-input">
        <textarea
          id="chat-input"
          placeholder="${placeholder}"
          rows="1"
          ${c.disable_paste ? "disabled" : ""}
        ></textarea>
        <button class="chat-send-btn" id="send-btn">➤</button>
      </div>
    `;

    // Clear button handler
    this.shadowRoot.getElementById("btn-clear").addEventListener("click", () => {
      this._messages = [];
      this._saveHistory();
      this._renderMessages();
    });
  }

  _renderMessages() {
    const container = this.shadowRoot.getElementById("messages");
    const emptyState = this.shadowRoot.getElementById("empty-state");

    if (this._messages.length === 0) {
      emptyState.style.display = "flex";
      // Remove all message elements
      container.querySelectorAll(".message").forEach((el) => el.remove());
      return;
    }

    emptyState.style.display = "none";

    // Build message HTML
    const messagesHtml = this._messages.map((msg) => {
      const role = msg.role === "user" ? (this._config.user_name || "You") : (this._config.assistant_name || "Hermes");
      const roleColor = msg.role === "user" ? (this._config.user_color || "#818cf8") : (this._config.assistant_color || "#34d399");
      return `
        <div class="message ${msg.role}">
          <div class="message-role" style="color: ${roleColor}">${role}</div>
          <div class="message-bubble">${this._escapeHtml(msg.content)}</div>
        </div>
      `;
    }).join("");

    // Replace only message elements, preserve empty state
    container.querySelectorAll(".message").forEach((el) => el.remove());
    container.insertAdjacentHTML("beforeend", messagesHtml);

    // Scroll to bottom
    container.scrollTop = container.scrollHeight;
  }

  _appendMessage(role, content) {
    this._messages.push({ role, content });
    if (this._messages.length > this._historyMax) {
      this._messages = this._messages.slice(-this._historyMax);
    }
    this._renderMessages();
    this._saveHistory();
  }

  _handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      this._handleSend();
    }
  }

  async _handleSend() {
    const textarea = this.shadowRoot.querySelector(".chat-input textarea");
    const text = textarea.value.trim();

    if (!text || this._isStreaming) return;

    textarea.value = "";
    this._resetTextareaHeight();

    this._appendMessage("user", text);
    await this._streamResponse(text);
  }

  async _streamResponse(userMessage) {
    const indicator = this.shadowRoot.getElementById("typing-indicator");
    const errorBanner = this.shadowRoot.getElementById("error-banner");
    indicator.classList.add("visible");
    errorBanner.classList.remove("visible");
    this._isStreaming = true;
    this._streamBuffer = "";

    try {
      // Build request to Hermes /v1/chat/completions
      const url = `${this._gatewayUrl}/v1/chat/completions`;
      const headers = {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${this._apiKey}`,
        "X-Hermes-Session-Id": this._conversationId,
      };

      const body = JSON.stringify({
        model: "default",
        messages: [
          {
            role: "system",
            content: "You are Hermes, an AI assistant integrated with Home Assistant. Be concise and helpful."
          },
          ...this._messages.map((m) => ({ role: m.role, content: m.content })),
        ],
        stream: true,
      });

      this._abortController = new AbortController();

      const response = await fetch(url, {
        method: "POST",
        headers,
        body,
        signal: this._abortController.signal,
      });

      if (!response.ok) {
        if (response.status === 401) throw new Error("Invalid API key");
        if (response.status === 403) throw new Error("Access forbidden");
        const errText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errText}`);
      }

      // Create placeholder for streaming response
      const container = this.shadowRoot.getElementById("messages");
      indicator.classList.remove("visible");

      const assistantMsg = {
        role: "assistant",
        content: "",
      };
      this._messages.push(assistantMsg);

      const msgEl = document.createElement("div");
      msgEl.className = "message assistant";
      msgEl.innerHTML = `
        <div class="message-role" style="color: ${this._config.assistant_color || "#34d399"}">${this._config.assistant_name || "Hermes"}</div>
        <div class="message-bubble"></div>
      `;
      container.appendChild(msgEl);
      const bubbleEl = msgEl.querySelector(".message-bubble");

      // Read SSE stream
      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n");

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const data = line.slice(6).trim();
          if (data === "[DONE]") continue;

          try {
            const parsed = JSON.parse(data);
            const delta = parsed.choices?.[0]?.delta?.content || "";
            if (delta) {
              this._streamBuffer += delta;
              assistantMsg.content += delta;
              bubbleEl.textContent = this._streamBuffer;
              container.scrollTop = container.scrollHeight;
            }
          } catch {}
        }
      }

    } catch (err) {
      indicator.classList.remove("visible");
      this._isStreaming = false;

      // Remove the empty assistant message if we failed
      const lastMsg = this._messages[this._messages.length - 1];
      if (lastMsg && lastMsg.role === "assistant" && !lastMsg.content) {
        this._messages.pop();
      }

      // Show error banner
      const errorEl = this.shadowRoot.getElementById("error-banner");
      errorEl.textContent = `Error: ${err.message}`;
      errorEl.classList.add("visible");

      setTimeout(() => errorEl.classList.remove("visible"), 8000);
    } finally {
      this._isStreaming = false;
      this._saveHistory();
    }
  }

  _resetTextareaHeight() {
    const textarea = this.shadowRoot.querySelector(".chat-input textarea");
    textarea.style.height = "auto";
  }

  _uuidv4() {
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      const v = c === "x" ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  _escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  _saveHistory() {
    try {
      const key = `hermes_history_${this._conversationId}`;
      const data = JSON.stringify(this._messages.slice(-this._historyMax));
      localStorage.setItem(key, data);
    } catch {}
  }

  _loadHistory() {
    try {
      const key = `hermes_history_${this._conversationId}`;
      const data = localStorage.getItem(key);
      if (data) {
        this._messages = JSON.parse(data);
        this._renderMessages();
      }
    } catch {
      this._messages = [];
    }
  }

  _setupResizeObserver() {
    if (!ResizeObserver) return;
    const root = this.shadowRoot.querySelector(".chat-messages");
    if (!root) return;
    new ResizeObserver(() => {
      root.scrollTop = root.scrollHeight;
    }).observe(root);
  }
}

customElements.define("hermes-chat-card", HermesChatCard);