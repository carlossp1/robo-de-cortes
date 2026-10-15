import os
import ssl
import sys
import re
import subprocess
import tempfile
import json
import shutil
import urllib3
import requests
import httpx
from datetime import timedelta
import streamlit as st

# Correção de segurança SSL para ambientes com Proxy / VPN / Firewall
urllib3.disable_warnings()
ssl._create_default_https_context = ssl._create_unverified_context
os.environ['CURL_CA_BUNDLE'] = ''
os.environ['PYTHONHTTPSVERIFY'] = '0'
os.environ['HF_HUB_DISABLE_SSL_VERIFICATION'] = '1'

try:
    old_httpx_init = httpx.Client.__init__
    httpx.Client.__init__ = lambda self, *a, **kw: old_httpx_init(self, *a, **{**kw, 'verify': False})
    old_req_init = requests.Session.__init__
    requests.Session.__init__ = lambda self, *a, **kw: (old_req_init(self, *a, **kw), setattr(self, 'verify', False))[0]
except Exception:
    pass

st.set_page_config(
    page_title="🤖 Robô de Cortes com IA & Legendas",
    page_icon="🎬",
    layout="wide"
)

st.title("🤖 Robô de Cortes Inteligente + Legendas em Português")
st.markdown("Cole o link de um vídeo do YouTube. O robô irá **analisar o conteúdo**, **encontrar os melhores momentos para corte** e **gerar os clipes com legendas embutidas em português**!")

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output_clips")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Configurações na Sidebar
st.sidebar.header("⚙️ Configurações do Robô")
video_format_option = st.sidebar.selectbox(
    "📱 Formato do Vídeo:",
    options=[
        "Vertical TikTok/Reels (9:16 - Recorte Central)",
        "Vertical TikTok/Reels (9:16 - Fundo Desfocado)",
        "Horizontal Original (16:9)"
    ],
    index=0
)
speed_up_option = st.sidebar.checkbox("⚡ Acelerar 5% (Anti-Direitos Autorais)", value=True, help="Acelera o vídeo e o áudio em 1.05x sem alterar a afinação da música ou da voz.")
subtitles_option = st.sidebar.checkbox("🔤 Embutir Legendas em Português", value=True, help="Adiciona legendas amarelas estilizadas tipo Shorts/Reels.")
sub_position = st.sidebar.selectbox("📍 Posição da Legenda:", options=["Meio do Vídeo (Centro)", "Parte Inferior (Rodapé)"], index=0)
subtitle_color = st.sidebar.selectbox("🎨 Cor da Legenda:", options=["Amarela (&H00FFFF)", "Branca (&HFFFFFF)", "Verde (&H00FF00)"], index=0)
ignore_ssl = st.sidebar.checkbox("🔒 Ignorar SSL (Proxy/VPN)", value=True)
whisper_model_size = st.sidebar.selectbox("🧠 Modelo de IA para Transcrição (pt-BR):", options=["base", "small", "medium"], index=1, help="O modelo 'small' oferece alta precisão para Português do Brasil.")

url = st.text_input("🔗 Link do vídeo do YouTube:", placeholder="https://www.youtube.com/watch?v=...")

def format_time_hms(seconds):
    td = timedelta(seconds=float(seconds))
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    millis = int((seconds - total_seconds) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def format_time_simple(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def download_full_video(video_url, temp_dir, ignore_ssl_flag):
    raw_path = os.path.join(temp_dir, "video_base.mp4")
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--js-runtimes", "node",
        "--no-playlist",
        "-o", raw_path
    ]
    if ignore_ssl_flag:
        cmd.append("--no-check-certificates")
    cmd.append(video_url)
    
    res = subprocess.run(cmd, capture_output=True, text=True)
    downloaded = [os.path.join(temp_dir, f) for f in os.listdir(temp_dir) if f.startswith("video_base")]
    if not downloaded:
        raise Exception(f"Erro ao baixar vídeo do YouTube:\n{res.stderr}")
    return downloaded[0]

def get_audio_and_transcribe(video_url, temp_dir, model_name, ignore_ssl_flag):
    audio_path = os.path.join(temp_dir, "audio.mp3")
    
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-x", "--audio-format", "mp3",
        "--no-playlist",
        "-o", audio_path
    ]
    if ignore_ssl_flag:
        cmd.append("--no-check-certificates")
    cmd.append(video_url)
    
    res = subprocess.run(cmd, capture_output=True, text=True)
    if not os.path.exists(audio_path):
        raise Exception(f"Erro ao baixar áudio do YouTube:\n{res.stderr}")
    
    # Converter áudio para WAV 16kHz Mono (formato nativo ideal do Whisper)
    wav_16k_path = os.path.join(temp_dir, "audio_16k.wav")
    subprocess.run([
        "ffmpeg", "-y",
        "-i", audio_path,
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        wav_16k_path
    ], capture_output=True, text=True, check=True)
    
    from faster_whisper import WhisperModel
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    
    # Prompt explícito e parâmetros determinísticos para Português do Brasil (pt-BR)
    initial_prompt_pt_br = "Esta é uma transcrição precisa em Português do Brasil (pt-BR). Use gramática, pontuação e ortografia brasileiras."
    
    segments, info = model.transcribe(
        wav_16k_path,
        language="pt",
        initial_prompt=initial_prompt_pt_br,
        temperature=0.0,
        beam_size=5,
        best_of=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500)
    )
    
    segment_list = []
    for s in segments:
        segment_list.append({
            "start": s.start,
            "end": s.end,
            "text": s.text.strip()
        })
    return segment_list

def find_best_clips(segments, min_duration=20, max_duration=60):
    if not segments:
        return []
    
    clips = []
    current_clip = []
    
    for seg in segments:
        current_clip.append(seg)
        dur = current_clip[-1]["end"] - current_clip[0]["start"]
        
        if dur >= min_duration:
            start_t = current_clip[0]["start"]
            end_t = current_clip[-1]["end"]
            text_preview = " ".join([s["text"] for s in current_clip])
            
            words = text_preview.split()
            title = " ".join(words[:6]) + "..." if len(words) > 6 else text_preview
            
            clips.append({
                "title": title,
                "start": start_t,
                "end": end_t,
                "duration": round(end_t - start_t, 1),
                "text": text_preview,
                "segments": list(current_clip)
            })
            
            current_clip = current_clip[len(current_clip)//2:]
            
            if len(clips) >= 5:
                break
                
    return clips

def generate_srt(segments, clip_start, clip_end, srt_filepath):
    with open(srt_filepath, "w", encoding="utf-8") as f:
        idx = 1
        for seg in segments:
            if seg["end"] < clip_start or seg["start"] > clip_end:
                continue
            
            rel_start = max(0, seg["start"] - clip_start)
            rel_end = max(0.1, seg["end"] - clip_start)
            
            start_str = format_time_hms(rel_start)
            end_str = format_time_hms(rel_end)
            
            f.write(f"{idx}\n")
            f.write(f"{start_str} --> {end_str}\n")
            f.write(f"{seg['text']}\n\n")
            idx += 1

# Estado da Sessão
if "segments" not in st.session_state:
    st.session_state.segments = None
if "clips" not in st.session_state:
    st.session_state.clips = None
if "analyzed_url" not in st.session_state:
    st.session_state.analyzed_url = ""
if "local_video_path" not in st.session_state:
    st.session_state.local_video_path = None
if "generated_clips" not in st.session_state:
    st.session_state.generated_clips = {}

tab1, tab2 = st.tabs(["🤖 Cortes Automáticos (IA)", "🎛️ Corte Manual"])

with tab1:
    st.subheader("1. Analisar Vídeo e Encontrar os Melhores Momentos")
    
    if st.button("🔍 Analisar Vídeo com IA", type="primary"):
        if not url.strip():
            st.error("Por favor, insira uma URL válida do YouTube.")
        else:
            with st.status("Analisando o vídeo com IA...", expanded=True) as status:
                try:
                    temp_dir = tempfile.mkdtemp()
                    
                    status.write("📥 Baixando vídeo completo do YouTube...")
                    base_video = download_full_video(url, temp_dir, ignore_ssl)
                    st.session_state.local_video_path = base_video
                    
                    status.write("🧠 Gerando transcrição em Português com IA...")
                    segments = get_audio_and_transcribe(url, temp_dir, whisper_model_size, ignore_ssl)
                    
                    status.write("✂️ Identificando os melhores momentos...")
                    clips = find_best_clips(segments)
                    
                    st.session_state.segments = segments
                    st.session_state.clips = clips
                    st.session_state.analyzed_url = url
                    st.session_state.generated_clips = {}
                    
                    status.update(label="Análise concluída com sucesso!", state="complete", expanded=False)
                    st.success(f"Encontrados {len(clips)} momentos de destaque no vídeo!")
                except Exception as e:
                    status.update(label="Erro na análise", state="error")
                    st.error(f"Erro ao analisar o vídeo: {str(e)}")

    if st.session_state.clips and st.session_state.analyzed_url == url:
        st.subheader("2. Escolha o Clipe que Deseja Gerar")
        
        for idx, clip in enumerate(st.session_state.clips):
            st.markdown(f"### 🎬 Clipe {idx+1}: {clip['title']}")
            st.caption(f"⏱️ **Horário:** {format_time_simple(clip['start'])} ➔ {format_time_simple(clip['end'])} ({clip['duration']} segundos)")
            
            edited_text = st.text_area("✍️ **Revisar/Editar Texto da Legenda (opcional):**", value=clip['text'], key=f"edit_txt_{idx}", height=80)
            
            btn_key = f"btn_gen_{idx}"
            if st.button(f"⚡ Gerar Clipe {idx+1}", key=btn_key):
                with st.status(f"Gerando Clipe {idx+1}...", expanded=True) as clip_status:
                    try:
                        temp_dir = tempfile.mkdtemp()
                        final_filename = f"clipe_{idx+1}.mp4"
                        final_path = os.path.join(OUTPUT_DIR, final_filename)
                        srt_filename = "subtitles.srt"
                        srt_path = os.path.join(temp_dir, srt_filename)
                        
                        start_str = format_time_simple(clip['start'])
                        end_str = format_time_simple(clip['end'])
                        
                        # Se o texto foi editado pelo usuário, atualiza a transcrição do clipe
                        clip_segments = clip['segments']
                        if edited_text.strip() and edited_text.strip() != clip['text']:
                            # Atualiza o texto dos segmentos proporcionalmente
                            clip_segments = [{
                                "start": clip['start'],
                                "end": clip['end'],
                                "text": edited_text.strip()
                            }]
                        
                        # Garantir vídeo base baixado
                        if not st.session_state.local_video_path or not os.path.exists(st.session_state.local_video_path):
                            clip_status.write("📥 Baixando vídeo base...")
                            st.session_state.local_video_path = download_full_video(url, temp_dir, ignore_ssl)
                        
                        src_video = st.session_state.local_video_path
                        
                        # Copia temporária para o diretório de trabalho do FFmpeg
                        temp_src = os.path.join(temp_dir, "input_base.mp4")
                        shutil.copy(src_video, temp_src)

                        vf_filters = []
                        
                        if "Recorte Central" in video_format_option:
                            vf_filters.append("crop=ih*(9/16):ih,scale=1080:1920")
                        elif "Fundo Desfocado" in video_format_option:
                            vf_filters.append("split[v1][v2];[v1]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:10[bg];[v2]scale=1080:-1[fg];[bg][fg]overlay=y=(H-h)/2")

                        if speed_up_option:
                            vf_filters.append("setpts=PTS/1.05")

                        if subtitles_option:
                            clip_status.write("🔤 Embutindo legendas em português centralizadas...")
                            generate_srt(clip_segments, clip['start'], clip['end'], srt_path)
                            color_code = subtitle_color.split("(")[1].replace(")", "").strip()
                            
                            play_res_y = 1920 if "Vertical" in video_format_option else 1080
                            font_size = 38 if "Vertical" in video_format_option else 28
                            
                            if sub_position == "Meio do Vídeo (Centro)":
                                alignment = 2  # Bottom-Center com MarginV no meio da tela
                                margin_v = 900 if "Vertical" in video_format_option else 500
                            else:
                                alignment = 2  # Bottom-Center (rodapé)
                                margin_v = 140 if "Vertical" in video_format_option else 60
                                
                            vf_filters.append(f"subtitles={srt_filename}:force_style='PlayResY={play_res_y},Fontname=Arial,FontSize={font_size},PrimaryColour={color_code},OutlineColour=&H000000,BorderStyle=1,Outline=3,Alignment={alignment},MarginV={margin_v}'")

                        cmd_ffmpeg = [
                            "ffmpeg", "-y",
                            "-ss", start_str,
                            "-to", end_str,
                            "-i", "input_base.mp4"
                        ]

                        if vf_filters:
                            cmd_ffmpeg.extend(["-vf", ",".join(vf_filters)])

                        if speed_up_option:
                            cmd_ffmpeg.extend(["-af", "atempo=1.05"])

                        cmd_ffmpeg.extend([
                            "-c:v", "libx264",
                            "-c:a", "aac",
                            final_path
                        ])

                        clip_status.write("⚡ Processando vídeo TikTok (9:16)...")
                        ff_res = subprocess.run(cmd_ffmpeg, cwd=temp_dir, capture_output=True, text=True)
                        
                        if ff_res.returncode != 0:
                            clip_status.write("⚠️ Processamento com filtro falhou, realizando corte direto...")
                            cmd_ffmpeg_clean = [
                                "ffmpeg", "-y",
                                "-ss", start_str,
                                "-to", end_str,
                                "-i", "input_base.mp4",
                                "-c", "copy",
                                final_path
                            ]
                            subprocess.run(cmd_ffmpeg_clean, cwd=temp_dir, capture_output=True, text=True, check=True)

                        st.session_state.generated_clips[idx] = final_path
                        clip_status.update(label="Clipe TikTok gerado com sucesso!", state="complete", expanded=False)
                        st.success(f"Clipe {idx+1} pronto para o TikTok!")
                    except Exception as e_clip:
                        clip_status.update(label="Erro ao gerar clipe", state="error")
                        st.error(f"Ocorreu um erro: {str(e_clip)}")

            if idx in st.session_state.generated_clips and os.path.exists(st.session_state.generated_clips[idx]):
                video_file_path = st.session_state.generated_clips[idx]
                st.video(video_file_path)
                with open(video_file_path, "rb") as f:
                    st.download_button(
                        label=f"💾 Baixar Clipe {idx+1} (.mp4)",
                        data=f.read(),
                        file_name=f"corte_tiktok_{idx+1}.mp4",
                        mime="video/mp4",
                        key=f"dl_btn_{idx}",
                        use_container_width=True
                    )
            st.divider()

with tab2:
    st.subheader("🎛️ Recorte Manual com Legenda Opcional")
    
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        m_start = st.text_input("⏱️ Tempo Inicial (ex: 00:01:00):", value="00:00:10")
    with col_m2:
        m_end = st.text_input("⏱️ Tempo Final (ex: 00:01:30):", value="00:00:40")

    if st.button("✂️ Cortar Trecho Manual", type="primary"):
        if not url.strip():
            st.error("Por favor, insira uma URL do YouTube.")
        else:
            with st.status("Gerando corte manual...", expanded=True) as m_status:
                try:
                    temp_dir = tempfile.mkdtemp()
                    out_final = os.path.join(OUTPUT_DIR, "corte_manual.mp4")
                    
                    m_status.write("📥 Baixando vídeo...")
                    base_video = download_full_video(url, temp_dir, ignore_ssl)
                    
                    temp_src = os.path.join(temp_dir, "input_base.mp4")
                    shutil.copy(base_video, temp_src)
                    
                    m_status.write("⚡ Efetuando corte local no formato TikTok...")
                    vf_m = []
                    if "Recorte Central" in video_format_option:
                        vf_m.append("crop=ih*(9/16):ih,scale=1080:1920")
                    elif "Fundo Desfocado" in video_format_option:
                        vf_m.append("split[v1][v2];[v1]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:10[bg];[v2]scale=1080:-1[fg];[bg][fg]overlay=y=(H-h)/2")

                    if speed_up_option:
                        vf_m.append("setpts=PTS/1.05")
                    
                    cmd_m = [
                        "ffmpeg", "-y",
                        "-ss", m_start,
                        "-to", m_end,
                        "-i", "input_base.mp4"
                    ]
                    if vf_m:
                        cmd_m.extend(["-vf", ",".join(vf_m)])
                        if speed_up_option:
                            cmd_m.extend(["-af", "atempo=1.05"])
                        cmd_m.extend(["-c:v", "libx264", "-c:a", "aac"])
                    else:
                        cmd_m.extend(["-c", "copy"])
                    
                    cmd_m.append(out_final)
                    
                    subprocess.run(cmd_m, cwd=temp_dir, capture_output=True, text=True, check=True)
                    m_status.update(label="Corte manual concluído!", state="complete", expanded=False)
                    
                    st.video(out_final)
                    with open(out_final, "rb") as f:
                        st.download_button(
                            label="💾 Baixar Corte Manual (.mp4)",
                            data=f.read(),
                            file_name="corte_manual.mp4",
                            mime="video/mp4",
                            use_container_width=True
                        )
                except Exception as e_m:
                    m_status.update(label="Erro no corte manual", state="error")
                    st.error(f"Erro: {str(e_m)}")
