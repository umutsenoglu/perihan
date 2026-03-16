OpenClaw uses https://github.com/WhiskeySockets/Baileys — an open-source Node.js library that implements the WhatsApp Web protocol. When you connected, you scanned a QR
  code, exactly like logging into WhatsApp Web. That's the entire "integration."                                                                                                                
                                                                                                                                                                                                  So the flow is:                                                                                                                                                                               
                                                                                                                                                                                                
  User visits your app → sees QR code → scans with phone                                                                                                                                          → your backend connects as a WhatsApp Web client via Baileys                                                                                                                                    → receives all messages in real-time                                                                                                                                                                                                                                                                                                                                                            No Android app needed. No ADB. No backup decryption. Just a QR code scan.                                                                                                                                                                                                                                                                                                                     
  What this means for your project:

  - Baileys is Node.js — your project is Python. The Python equivalent is pywa or whatsapp-web.js running as a sidecar service
  - Or you could run a small Baileys Node.js service alongside your FastAPI app that forwards messages to your API
  - For historical messages: once connected via Baileys, you can fetch chat history via the WhatsApp Web protocol too — not just new messages

  The honest reality on ToS:

  OpenClaw does this, many products do this. WhatsApp is aware and tolerates it at small personal scale. At large commercial scale Meta may take action. OpenClaw accepts this risk openly —    
  that's the industry norm for personal AI assistants.

  For your use case — personal + small user base — the QR code / Baileys approach is exactly the right answer. It's what real products ship.

  Want to design how this would integrate into your existing FastAPI + ChromaDB architecture?

  Sources:
  - https://docs.openclaw.ai/channels/whatsapp
  - https://www.marktechpost.com/2026/02/14/getting-started-with-openclaw-and-connecting-it-with-whatsapp/
  - https://openclaw.ai/