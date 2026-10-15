---
title: Robo de Cortes com IA
emoji: 🎬
colorFrom: red
colorTo: purple
sdk: streamlit
sdk_version: 1.38.0
app_file: app.py
pinned: false
---

# 🎬 Robô de Cortes Inteligente com IA & Legendas Automáticas

Aplicação Web moderna desenvolvida em Python + Streamlit para criar cortes verticais (formato 9:16 para TikTok, Reels e YouTube Shorts) a partir de links de vídeos do YouTube.

## 🚀 Funcionalidades

- **Análise Inteligente por IA:** Transcrição em Português do Brasil com Whisper e detecção dos melhores momentos.
- **Formato Vertical Automático:** Recorte central 9:16 ou formato com fundo desfocado.
- **Legendas Estilizadas:** Legendas automáticas queimadas no vídeo (Hardsub) com cores customizáveis e posição ajustável.
- **Modo Anti-Copyright:** Aceleração de 5% (1.05x) no áudio e vídeo mantendo a afinação original.
- **Corte Manual ou Automático:** Permite cortar trechos com minutos/segundos exatos.

---

## ☁️ Como Publicar na Nuvem (Gratuito)

### Opção 1: Streamlit Community Cloud (Recomendado)
1. Suba este projeto para um repositório no seu GitHub.
2. Acesse [share.streamlit.io](https://share.streamlit.io/) e faça login com seu GitHub.
3. Clique em **"New app"**.
4. Selecione o repositório, a branch (`main`) e o arquivo principal `app.py`.
5. Clique em **"Deploy"**. O Streamlit Cloud instalará o FFmpeg e o Python automaticamente via `packages.txt` e `requirements.txt`.

### Opção 2: Hugging Face Spaces
1. Crie uma conta em [huggingface.co](https://huggingface.co/).
2. Clique em **New Space** e selecione **Streamlit**.
3. Conecte ao seu repositório GitHub ou faça o clone/push dos arquivos diretamente.
4. O app será compilado e disponibilizado publicamente com suporte a CPU e 16 GB de RAM.

---

## 💻 Executar Localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```
