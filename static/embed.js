(function () {
    const currentScript = document.currentScript || (function () {
        const scripts = document.getElementsByTagName('script');
        return scripts[scripts.length - 1];
    })();

    const rawTenantId = currentScript.getAttribute('data-tenant-id') || 'default';
    const apiHost = currentScript.getAttribute('data-api-host') || '';
    const position = currentScript.getAttribute('data-position') || 'bottom-right';

    class RagChatWidget extends HTMLElement {
        constructor() {
            super();
            this.attachShadow({ mode: 'open' });
            this.isOpen = false;
            this.tenantConfig = {
                tenant_id: rawTenantId,
                bot_name: currentScript.getAttribute('data-title') || 'Support Assistant',
                theme_color: currentScript.getAttribute('data-theme-color') || '#2563eb',
                greeting_message: 'Hello! How can I help you today?',
                fallback_message: 'I do not have sufficient information.'
            };
        }

        async connectedCallback() {
            // 1. Bootstrap tenant settings dynamically from backend
            try {
                const res = await fetch(`${apiHost}/api/v1/tenant/${encodeURIComponent(rawTenantId)}/config`);
                if (res.ok) {
                    const remoteConfig = await res.json();
                    // Remote config overrides defaults, unless host script explicitly set attributes
                    this.tenantConfig.bot_name = currentScript.getAttribute('data-title') || remoteConfig.bot_name;
                    this.tenantConfig.theme_color = currentScript.getAttribute('data-theme-color') || remoteConfig.theme_color;
                    this.tenantConfig.greeting_message = remoteConfig.greeting_message;
                    this.tenantConfig.fallback_message = remoteConfig.fallback_message;
                }
            } catch (e) {
                console.warn('[RAG Widget] Bootstrapped with fallback local config.');
            }

            this.render();
            this.bindEvents();
        }

        render() {
            const isLeft = position === 'bottom-left';
            const posStyle = isLeft ? 'left: 24px;' : 'right: 24px;';
            const c = this.tenantConfig;

            this.shadowRoot.innerHTML = `
        <style>
          :host {
            --primary: ${c.theme_color};
            --font: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            all: initial;
            font-family: var(--font);
          }
          *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; font-family: inherit; }

          #launcher-btn {
            position: fixed;
            bottom: 24px;
            ${posStyle}
            width: 58px;
            height: 58px;
            border-radius: 50%;
            background-color: var(--primary);
            color: #ffffff;
            border: none;
            cursor: pointer;
            box-shadow: 0 4px 14px rgba(0,0,0,0.22);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 26px;
            z-index: 2147483647;
            transition: transform 0.2s ease;
          }
          #launcher-btn:hover { transform: scale(1.08); }

          #chat-window {
            position: fixed;
            bottom: 96px;
            ${posStyle}
            width: 380px;
            height: 540px;
            max-width: calc(100vw - 48px);
            max-height: calc(100vh - 120px);
            background: #ffffff;
            border-radius: 14px;
            box-shadow: 0 12px 36px rgba(0,0,0,0.16);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            border: 1px solid #e2e8f0;
            z-index: 2147483647;
            opacity: 0;
            transform: translateY(20px) scale(0.96);
            pointer-events: none;
            transition: opacity 0.2s ease, transform 0.2s ease;
          }
          #chat-window.open {
            opacity: 1;
            transform: translateY(0) scale(1);
            pointer-events: auto;
          }

          .header {
            background-color: var(--primary);
            color: #ffffff;
            padding: 14px 18px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-weight: 600;
            font-size: 15px;
          }
          .close-btn { background: transparent; border: none; color: #fff; font-size: 22px; cursor: pointer; }

          .messages {
            flex: 1;
            padding: 16px;
            overflow-y: auto;
            background: #f8fafc;
            display: flex;
            flex-direction: column;
            gap: 12px;
          }
          .msg {
            max-width: 82%;
            padding: 10px 14px;
            border-radius: 10px;
            font-size: 13.5px;
            line-height: 1.45;
            word-wrap: break-word;
          }
          .msg.user {
            align-self: flex-end;
            background: var(--primary);
            color: #ffffff;
            border-bottom-right-radius: 2px;
          }
          .msg.bot {
            align-self: flex-start;
            background: #ffffff;
            color: #0f172a;
            border: 1px solid #e2e8f0;
            border-bottom-left-radius: 2px;
          }

          .sources {
            margin-top: 8px;
            padding-top: 6px;
            border-top: 1px dashed #cbd5e1;
            font-size: 11px;
            color: #64748b;
          }
          .source-badge {
            display: inline-block;
            background: #e2e8f0;
            color: #334155;
            padding: 2px 6px;
            border-radius: 4px;
            margin: 2px 4px 2px 0;
            font-weight: 500;
          }

          .typing {
            display: flex;
            gap: 4px;
            padding: 10px 14px;
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            align-self: flex-start;
          }
          .dot {
            width: 6px; height: 6px; background: #94a3b8; border-radius: 50%;
            animation: pulse 1.4s infinite ease-in-out both;
          }
          .dot:nth-child(1) { animation-delay: -0.32s; }
          .dot:nth-child(2) { animation-delay: -0.16s; }
          @keyframes pulse {
            0%, 80%, 100% { transform: scale(0); }
            40% { transform: scale(1); }
          }

          .input-form { display: flex; padding: 12px; background: #fff; border-top: 1px solid #e2e8f0; }
          .input-form input {
            flex: 1; padding: 9px 12px; border: 1px solid #cbd5e1;
            border-radius: 6px; font-size: 13.5px; outline: none;
          }
          .input-form input:focus { border-color: var(--primary); }
          .input-form button {
            margin-left: 8px; background: var(--primary); color: #fff; border: none;
            padding: 0 16px; border-radius: 6px; font-weight: 500; cursor: pointer;
          }
          .input-form button:disabled { opacity: 0.6; cursor: not-allowed; }
        </style>

        <button id="launcher-btn" aria-label="Open Chat">💬</button>

        <div id="chat-window">
          <div class="header">
            <span>${c.bot_name}</span>
            <button class="close-btn" id="close-btn">&times;</button>
          </div>
          <div class="messages" id="messages-box">
            <div class="msg bot">${c.greeting_message}</div>
          </div>
          <form class="input-form" id="input-form">
            <input type="text" id="query-input" placeholder="Type your message..." autocomplete="off" required />
            <button type="submit" id="submit-btn">Send</button>
          </form>
        </div>
      `;
        }

        bindEvents() {
            const launcher = this.shadowRoot.getElementById('launcher-btn');
            const closeBtn = this.shadowRoot.getElementById('close-btn');
            const chatWindow = this.shadowRoot.getElementById('chat-window');
            const form = this.shadowRoot.getElementById('input-form');
            const input = this.shadowRoot.getElementById('query-input');

            const toggleChat = () => {
                this.isOpen = !this.isOpen;
                chatWindow.classList.toggle('open', this.isOpen);
                if (this.isOpen) setTimeout(() => input.focus(), 150);
            };

            launcher.addEventListener('click', toggleChat);
            closeBtn.addEventListener('click', toggleChat);

            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                const text = input.value.trim();
                if (!text) return;

                this.appendMessage(text, 'user');
                input.value = '';
                input.disabled = true;
                this.shadowRoot.getElementById('submit-btn').disabled = true;
                this.showTyping();

                try {
                    const endpoint = `${apiHost}/api/v1/tenant/${encodeURIComponent(this.tenantConfig.tenant_id)}/chat`;
                    const res = await fetch(endpoint, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message: text, top_k: 3 })
                    });

                    if (!res.ok) throw new Error(`HTTP ${res.status}`);
                    const data = await res.json();
                    this.hideTyping();
                    this.appendMessage(data.reply, 'bot', data.fallback_triggered ? [] : data.sources);
                } catch (err) {
                    this.hideTyping();
                    this.appendMessage('Could not reach the assistant service.', 'bot');
                } finally {
                    input.disabled = false;
                    this.shadowRoot.getElementById('submit-btn').disabled = false;
                    input.focus();
                }
            });
        }

        appendMessage(text, sender, sources = []) {
            const box = this.shadowRoot.getElementById('messages-box');
            const msg = document.createElement('div');
            msg.className = `msg ${sender}`;
            msg.textContent = text;

            if (sources && sources.length > 0) {
                const srcContainer = document.createElement('div');
                srcContainer.className = 'sources';
                srcContainer.textContent = 'Sources: ';
                sources.forEach(s => {
                    const badge = document.createElement('span');
                    badge.className = 'source-badge';
                    badge.textContent = `${s.metadata.source} (#${s.metadata.chunk_index})`;
                    srcContainer.appendChild(badge);
                });
                msg.appendChild(srcContainer);
            }

            box.appendChild(msg);
            box.scrollTop = box.scrollHeight;
        }

        showTyping() {
            const box = this.shadowRoot.getElementById('messages-box');
            const t = document.createElement('div');
            t.className = 'typing';
            t.id = 'typing-dots';
            t.innerHTML = '<div class="dot"></div><div class="dot"></div><div class="dot"></div>';
            box.appendChild(t);
            box.scrollTop = box.scrollHeight;
        }

        hideTyping() {
            const t = this.shadowRoot.getElementById('typing-dots');
            if (t) t.remove();
        }
    }

    if (!customElements.get('rag-chat-widget')) {
        customElements.define('rag-chat-widget', RagChatWidget);
    }

    const widgetInstance = document.createElement('rag-chat-widget');
    document.body.appendChild(widgetInstance);
})();