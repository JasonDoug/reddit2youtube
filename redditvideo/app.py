import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
from datetime import datetime
import time

from src.reddit import fetch_top_posts, fetch_hot_posts, search_subreddits
from src.script_generator import generate_script, PRESETS, PROVIDERS, OPENROUTER_MODELS, OPENAI_REPLIT_MODELS
from src.voiceover import generate_voiceover, GTTS_LANGUAGES
from src.image_pipeline import prepare_images_for_video, fetch_stock_image
from src.video_assembler import assemble_video
from src.analytics import log_search, log_script, log_video, log_publish, get_stats
from src.youtube_uploader import upload_to_youtube, is_youtube_configured

st.set_page_config(
    page_title="Reddit Video Pipeline",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

OUTPUT_DIR = Path(__file__).parent / "output"

# ── Session state defaults ──────────────────────────────────────────────────
for key, default in {
    "posts": [],
    "selected_post": None,
    "script": None,
    "voiceover": None,
    "images": [],
    "video": None,
    "step": 1,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ── Sidebar navigation ──────────────────────────────────────────────────────
with st.sidebar:
    st.title("🎬 Reddit Video Pipeline")
    st.markdown("---")
    page = st.radio(
        "Navigation",
        ["⚡ Pipeline Runner", "🔍 Search Reddit", "✍️ Script Generator", "🎙️ Voiceover", "🖼️ Images", "🎥 Assemble Video", "📊 Analytics"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.caption("Build viral videos from Reddit content")

    if st.session_state.selected_post:
        st.success(f"Post selected: {st.session_state.selected_post['title'][:40]}...")
    if st.session_state.script:
        st.success("✅ Script ready")
    if st.session_state.voiceover and "path" in st.session_state.voiceover:
        st.success("✅ Voiceover ready")
    if st.session_state.images:
        st.success(f"✅ {len(st.session_state.images)} images ready")
    if st.session_state.video and "path" in st.session_state.video:
        st.success("✅ Video assembled")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — SEARCH REDDIT
# ══════════════════════════════════════════════════════════════════════════════
if page == "🔍 Search Reddit":
    st.header("🔍 Search Reddit for Top Posts")

    col1, col2 = st.columns([2, 1])
    with col1:
        subreddit_input = st.text_input(
            "Subreddit(s)",
            placeholder="e.g. worldnews, AskReddit, todayilearned",
            help="Separate multiple subreddits with commas. You can include or omit the 'r/' prefix.",
        )
    with col2:
        sort_mode = st.selectbox("Sort by", ["Top", "Hot"])

    col3, col4, col5, col6 = st.columns(4)
    with col3:
        time_filter = st.selectbox(
            "Time range", ["day", "week", "month", "year", "all"],
            index=1,
            disabled=(sort_mode == "Hot"),
        )
    with col4:
        limit = st.slider("Max posts", 5, 50, 10)
    with col5:
        min_score = st.number_input("Min score", min_value=0, value=100, step=100)
    with col6:
        post_type = st.selectbox("Post type", ["all", "text", "link", "image", "video"])

    if st.button("🔎 Search", type="primary", use_container_width=True):
        if not subreddit_input.strip():
            st.error("Please enter at least one subreddit.")
        else:
            subreddits = [s.strip() for s in subreddit_input.split(",") if s.strip()]
            with st.spinner(f"Fetching posts from r/{', r/'.join(subreddits)}..."):
                try:
                    if sort_mode == "Top":
                        posts = fetch_top_posts(subreddits, time_filter, limit, min_score, post_type)
                    else:
                        posts = fetch_hot_posts(subreddits, limit)

                    errors = [p for p in posts if "error" in p]
                    valid_posts = [p for p in posts if "error" not in p]

                    for e in errors:
                        st.error(f"r/{e['subreddit']}: {e['error']}")

                    st.session_state.posts = valid_posts
                    log_search(subreddits, time_filter if sort_mode == "Top" else "hot", len(valid_posts))

                    if valid_posts:
                        st.success(f"Found {len(valid_posts)} posts!")
                except Exception as ex:
                    st.error(f"Error: {ex}")

    if st.session_state.posts:
        st.markdown("---")
        st.subheader(f"📋 Results ({len(st.session_state.posts)} posts)")

        df = pd.DataFrame([
            {
                "Rank": i + 1,
                "Title": p["title"][:80] + ("..." if len(p["title"]) > 80 else ""),
                "Subreddit": f"r/{p['subreddit']}",
                "Score": f"{p['score']:,}",
                "Comments": f"{p['num_comments']:,}",
                "Ratio": f"{p['upvote_ratio']:.0%}",
                "Awards": p.get("awards", 0),
                "Author": p["author"],
            }
            for i, p in enumerate(st.session_state.posts)
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.markdown("### Select a post to use")
        for i, post in enumerate(st.session_state.posts):
            with st.expander(f"#{i+1} — {post['title'][:90]} | ⬆️ {post['score']:,}"):
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.write(f"**Subreddit:** r/{post['subreddit']}")
                    st.write(f"**Score:** {post['score']:,} | **Comments:** {post['num_comments']:,} | **Ratio:** {post['upvote_ratio']:.0%}")
                    if post.get("selftext"):
                        st.write("**Content preview:**")
                        st.caption(post["selftext"][:300] + "...")
                    st.markdown(f"[View on Reddit]({post['permalink']})")
                with col_b:
                    if st.button("✅ Use this post", key=f"select_{i}", use_container_width=True):
                        st.session_state.selected_post = post
                        st.session_state.script = None
                        st.session_state.voiceover = None
                        st.session_state.images = []
                        st.session_state.video = None
                        st.success(f"Selected: {post['title'][:50]}...")
                        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — SCRIPT GENERATOR
# ══════════════════════════════════════════════════════════════════════════════
elif page == "✍️ Script Generator":
    st.header("✍️ Script Generator")

    if not st.session_state.selected_post:
        st.info("👈 Go to **Search Reddit** first and select a post.")
        st.stop()

    post = st.session_state.selected_post
    st.info(f"**Selected post:** {post['title']} | r/{post['subreddit']} | ⬆️ {post['score']:,}")

    col1, col2, col3 = st.columns(3)
    with col1:
        preset = st.selectbox("Platform Preset", list(PRESETS.keys()))
    with col2:
        genre = st.selectbox("Genre", [
            "Informative / Educational",
            "Entertaining / Funny",
            "Shocking / Controversial",
            "Heartwarming / Inspirational",
            "News / Current Events",
            "Opinion / Commentary",
            "Story Time / Narrative",
            "Mystery / Suspense",
        ])
    with col3:
        language_hint = st.selectbox("Script Language", ["English", "Spanish", "French", "German", "Portuguese"])

    if preset == "Custom":
        c1, c2 = st.columns(2)
        with c1:
            custom_duration = st.slider("Target duration (seconds)", 15, 600, 90)
        with c2:
            custom_style = st.text_input("Style notes", placeholder="e.g. calm narration, documentary style")
    else:
        p = PRESETS[preset]
        st.caption(f"⏱️ {p['duration_sec']}s · ~{p['word_count']} words · {p['aspect_ratio']} · {p['platform']}")
        custom_duration = p["duration_sec"]
        custom_style = ""

    st.markdown("---")
    st.subheader("🤖 AI Provider")

    provider_label = st.selectbox("Inference provider", list(PROVIDERS.keys()))
    provider_key = PROVIDERS[provider_label]

    ollama_base_url = ""
    ollama_api_key = ""

    if provider_key == "openai_replit":
        selected_model = st.selectbox("Model", OPENAI_REPLIT_MODELS, index=1)
        st.caption("Uses Replit AI Integrations — no API key required. Charges billed to your Replit credits.")

    elif provider_key == "openrouter_replit":
        selected_model = st.selectbox("Model", OPENROUTER_MODELS)
        st.caption("Uses OpenRouter via Replit AI Integrations — no API key required. Charges billed to your Replit credits.")
        st.caption("Models marked `:free` have no per-token cost.")

    else:  # ollama_cloud
        ollama_base_url = st.text_input(
            "Ollama Cloud base URL",
            value=os.environ.get("OLLAMA_CLOUD_BASE_URL", ""),
            placeholder="https://your-ollama-cloud-host/v1",
            help="The /v1 endpoint of your Ollama Cloud instance. Set OLLAMA_CLOUD_BASE_URL as a secret to persist this.",
        )
        ollama_api_key = st.text_input(
            "API key (optional)",
            value=os.environ.get("OLLAMA_CLOUD_API_KEY", ""),
            type="password",
            help="Leave blank if your Ollama Cloud instance does not require auth. Set OLLAMA_CLOUD_API_KEY as a secret to persist this.",
        )
        selected_model = st.text_input(
            "Model name",
            value="llama3.3",
            placeholder="e.g. llama3.3, mistral, qwen2.5:72b",
            help="Exact model tag as it appears in your Ollama instance.",
        )
        if not ollama_base_url:
            st.warning("Enter your Ollama Cloud base URL above, or add OLLAMA_CLOUD_BASE_URL as a Replit secret.")

    st.markdown("---")
    extra = st.text_area("Extra instructions (optional)", placeholder="e.g. mention the comments section, add a disclaimer, focus on a specific angle...")

    if st.button("🪄 Generate Script", type="primary", use_container_width=True):
        with st.spinner(f"Generating script with {provider_label} / {selected_model}..."):
            try:
                result = generate_script(
                    post=post,
                    preset_name=preset,
                    genre=genre,
                    custom_duration=custom_duration,
                    custom_style=custom_style,
                    extra_instructions=extra,
                    provider=provider_key,
                    model=selected_model,
                    ollama_base_url=ollama_base_url,
                    ollama_api_key=ollama_api_key,
                )
                st.session_state.script = result
                log_script(post["title"], result["platform"], genre, result["estimated_word_count"])
                st.success(f"Script generated with {result['provider']} / {result['model']}!")
            except Exception as ex:
                st.error(f"Error generating script: {ex}")

    if st.session_state.script:
        s = st.session_state.script
        st.markdown("---")
        st.subheader("📄 Generated Script")

        col_m, col_s = st.columns([3, 1])
        with col_s:
            st.metric("Words", s["estimated_word_count"])
            st.metric("Platform", s["platform"])
            st.metric("Target", f"{s['target_duration_sec']}s")
            st.metric("Ratio", s["aspect_ratio"])

        with col_m:
            hook_edit = st.text_area("🪝 Hook", s["hook"], height=80)
            main_edit = st.text_area("📝 Main Script", s["main_script"], height=200)
            cta_edit = st.text_area("📣 Call to Action", s["cta"], height=80)

            if st.button("💾 Save edits"):
                st.session_state.script["hook"] = hook_edit
                st.session_state.script["main_script"] = main_edit
                st.session_state.script["cta"] = cta_edit
                st.session_state.script["full_script"] = f"{hook_edit}\n\n{main_edit}\n\n{cta_edit}".strip()
                st.success("Saved!")

        st.markdown("**Image prompts for slideshow:**")
        for prompt in s.get("image_prompts", []):
            st.caption(f"• {prompt}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — VOICEOVER
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🎙️ Voiceover":
    st.header("🎙️ Generate Voiceover")

    if not st.session_state.script:
        st.info("👈 Go to **Script Generator** first.")
        st.stop()

    s = st.session_state.script
    st.info(f"**Script:** {len(s['full_script'].split())} words · {s['platform']}")

    col1, col2, col3 = st.columns(3)
    with col1:
        language = st.selectbox("Language", list(GTTS_LANGUAGES.keys()))
    with col2:
        speed = st.selectbox("Speed", ["Normal", "Slow"])
    with col3:
        section = st.selectbox("Script section", ["Full Script", "Hook only", "Main Script only"])

    script_text = {
        "Full Script": s["full_script"],
        "Hook only": s["hook"],
        "Main Script only": s["main_script"],
    }[section]

    st.text_area("Script to narrate", script_text, height=150, disabled=True)

    if st.button("🎙️ Generate Voiceover", type="primary", use_container_width=True):
        with st.spinner("Generating voiceover with gTTS (free)..."):
            try:
                result = generate_voiceover(
                    script=script_text,
                    language=language,
                    speed=speed,
                )
                if "error" in result:
                    st.error(result["error"])
                else:
                    st.session_state.voiceover = result
                    st.success(f"Voiceover generated! Duration: {result['duration_sec']:.1f}s")
            except Exception as ex:
                st.error(f"Error: {ex}")

    if st.session_state.voiceover and "path" in st.session_state.voiceover:
        v = st.session_state.voiceover
        st.markdown("---")
        st.subheader("🎧 Voiceover Preview")
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Duration", f"{v['duration_sec']:.1f}s")
        col_b.metric("Words", v["word_count"])
        col_c.metric("Language", v["language"])

        audio_path = v["path"]
        if os.path.exists(audio_path):
            with open(audio_path, "rb") as af:
                st.audio(af.read(), format="audio/mp3")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 4 — IMAGES
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🖼️ Images":
    st.header("🖼️ Image Slideshow")

    if not st.session_state.script:
        st.info("👈 Go to **Script Generator** first.")
        st.stop()

    s = st.session_state.script
    prompts = s.get("image_prompts", [])

    st.subheader("Image Prompts")
    st.caption("These were generated from your script. You can edit them below.")

    edited_prompts = []
    for i, p in enumerate(prompts):
        ep = st.text_input(f"Image {i+1}", p, key=f"prompt_{i}")
        edited_prompts.append(ep)

    add_prompt = st.text_input("Add additional image prompt", placeholder="e.g. dramatic sunset over a city skyline")
    if add_prompt:
        edited_prompts.append(add_prompt)

    col1, col2 = st.columns(2)
    with col1:
        use_stock = st.toggle("Use stock photos (Unsplash/Pexels)", value=True,
                              help="If no API key is set, styled placeholder images will be used.")
    with col2:
        aspect = st.selectbox("Aspect ratio", ["16:9", "9:16", "1:1", "4:3"],
                              index=["16:9", "9:16", "1:1", "4:3"].index(s.get("aspect_ratio", "16:9")))

    if not os.environ.get("UNSPLASH_ACCESS_KEY") and not os.environ.get("PEXELS_API_KEY"):
        st.info("💡 No stock photo API key found. Stylized placeholder images will be generated. "
                "Add UNSPLASH_ACCESS_KEY or PEXELS_API_KEY as a secret for real stock photos.")

    if st.button("🖼️ Fetch Images", type="primary", use_container_width=True):
        final_prompts = [p for p in edited_prompts if p.strip()]
        if not final_prompts:
            st.error("Add at least one image prompt.")
        else:
            with st.spinner(f"Fetching {len(final_prompts)} images..."):
                try:
                    paths = prepare_images_for_video(final_prompts, use_stock=use_stock, aspect_ratio=aspect)
                    st.session_state.images = paths
                    st.session_state.script["image_prompts"] = final_prompts
                    st.success(f"Got {len(paths)} images!")
                except Exception as ex:
                    st.error(f"Error: {ex}")

    if st.session_state.images:
        st.markdown("---")
        st.subheader("Preview")
        cols = st.columns(min(len(st.session_state.images), 3))
        for i, img_path in enumerate(st.session_state.images):
            if os.path.exists(img_path):
                cols[i % 3].image(img_path, caption=f"Image {i+1}", use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 5 — ASSEMBLE VIDEO
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🎥 Assemble Video":
    st.header("🎥 Assemble & Export Video")

    missing = []
    if not st.session_state.script:
        missing.append("Script")
    if not st.session_state.voiceover or "path" not in st.session_state.voiceover:
        missing.append("Voiceover")
    if not st.session_state.images:
        missing.append("Images")
    if missing:
        st.info(f"👈 Complete these steps first: {', '.join(missing)}")
        st.stop()

    s = st.session_state.script
    v = st.session_state.voiceover

    st.subheader("Video Settings")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        ken_burns = st.toggle("Ken Burns effect", value=True, help="Subtle zoom/pan animation on each image")
    with col2:
        fps = st.selectbox("FPS", [24, 30, 60], index=1)
    with col3:
        aspect = st.selectbox("Aspect ratio", ["16:9", "9:16", "1:1", "4:3"],
                              index=["16:9", "9:16", "1:1", "4:3"].index(s.get("aspect_ratio", "16:9")))
    with col4:
        transition = st.slider("Transition (s)", 0.0, 2.0, 0.5, 0.1)

    post = st.session_state.selected_post or {}
    safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in post.get("title", "video")[:40])
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{safe_title}_{ts}.mp4"

    st.caption(f"Output: {output_filename}")
    st.caption(f"Images: {len(st.session_state.images)} · Audio: {v['duration_sec']:.1f}s · ~{len(st.session_state.images)} slides")

    if st.button("🎬 Assemble Video", type="primary", use_container_width=True):
        with st.spinner("Assembling video... this may take 1-3 minutes depending on length."):
            try:
                result = assemble_video(
                    image_paths=st.session_state.images,
                    audio_path=v["path"],
                    output_filename=output_filename,
                    aspect_ratio=aspect,
                    ken_burns=ken_burns,
                    transition_duration=transition,
                    fps=fps,
                )
                if "error" in result:
                    st.error(f"Assembly failed: {result['error']}")
                else:
                    st.session_state.video = result
                    log_video(
                        post_title=post.get("title", ""),
                        platform=s["platform"],
                        genre=s["genre"],
                        duration_sec=result["duration_sec"],
                        file_size_mb=result["file_size_mb"],
                        video_path=result["path"],
                        audio_path=v["path"],
                        num_images=len(st.session_state.images),
                    )
                    st.success(f"Video assembled! {result['duration_sec']:.1f}s · {result['file_size_mb']}MB")
            except Exception as ex:
                st.error(f"Error: {ex}")

    if st.session_state.video and "path" in st.session_state.video:
        vd = st.session_state.video
        st.markdown("---")
        st.subheader("✅ Video Ready")

        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("Duration", f"{vd['duration_sec']:.1f}s")
        col_b.metric("Size", f"{vd['file_size_mb']} MB")
        col_c.metric("Resolution", vd["resolution"])
        col_d.metric("Images used", vd["num_images"])

        video_path = vd["path"]
        if os.path.exists(video_path):
            with open(video_path, "rb") as vf:
                video_bytes = vf.read()
            st.video(video_bytes)
            st.download_button(
                "⬇️ Download Video",
                data=video_bytes,
                file_name=vd["filename"],
                mime="video/mp4",
                use_container_width=True,
            )

        st.markdown("---")
        st.subheader("🚀 Publish to YouTube")

        if not is_youtube_configured():
            st.warning(
                "YouTube upload not configured. To enable it:\n\n"
                "1. Go to [Google Cloud Console](https://console.cloud.google.com/)\n"
                "2. Create a project → Enable YouTube Data API v3\n"
                "3. Create OAuth2 credentials (Desktop app)\n"
                "4. Download the JSON and paste its content as the `YOUTUBE_CLIENT_SECRETS_JSON` secret."
            )
        else:
            yt_title = st.text_input("YouTube title", post.get("title", "")[:100])
            yt_desc = st.text_area("Description", f"Based on: {post.get('permalink', '')}\n\nGenerated with Reddit Video Pipeline.")
            yt_tags = st.text_input("Tags (comma-separated)", f"{post.get('subreddit', '')}, reddit, viral")
            yt_privacy = st.selectbox("Privacy", ["private", "unlisted", "public"])

            if st.button("🎬 Upload to YouTube", type="primary"):
                with st.spinner("Uploading to YouTube..."):
                    result = upload_to_youtube(
                        video_path=video_path,
                        title=yt_title,
                        description=yt_desc,
                        tags=[t.strip() for t in yt_tags.split(",")],
                        privacy=yt_privacy,
                    )
                    if "error" in result:
                        st.error(f"Upload failed: {result['error']}")
                    else:
                        log_publish(video_path, "YouTube", result["url"], "success")
                        st.success(f"Uploaded! [View on YouTube]({result['url']})")
                        st.balloons()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 6 — ANALYTICS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📊 Analytics":
    st.header("📊 Usage Analytics")

    stats = get_stats()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Searches", stats["total_searches"])
    col2.metric("Scripts Generated", stats["total_scripts"])
    col3.metric("Videos Created", stats["total_videos"])
    col4.metric("Published", stats["total_publishes"])

    if stats["total_videos"] > 0:
        c1, c2 = st.columns(2)
        c1.metric("Total Video Duration", f"{stats['total_duration_sec'] / 60:.1f} min")
        c2.metric("Total Storage Used", f"{stats['total_size_mb']:.1f} MB")

    st.markdown("---")

    col_left, col_right = st.columns(2)

    with col_left:
        if stats["platform_counts"]:
            st.subheader("Videos by Platform")
            fig = px.pie(
                names=list(stats["platform_counts"].keys()),
                values=list(stats["platform_counts"].values()),
                hole=0.4,
            )
            fig.update_layout(margin=dict(t=20, b=20, l=20, r=20), height=300)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.subheader("Videos by Platform")
            st.caption("No videos yet.")

    with col_right:
        if stats["genre_counts"]:
            st.subheader("Videos by Genre")
            fig2 = px.bar(
                x=list(stats["genre_counts"].values()),
                y=list(stats["genre_counts"].keys()),
                orientation="h",
            )
            fig2.update_layout(margin=dict(t=20, b=20, l=20, r=20), height=300, xaxis_title="Count", yaxis_title="")
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.subheader("Videos by Genre")
            st.caption("No videos yet.")

    if stats["subreddit_counts"]:
        st.subheader("Most Searched Subreddits")
        sub_df = pd.DataFrame([
            {"Subreddit": f"r/{k}", "Searches": v}
            for k, v in sorted(stats["subreddit_counts"].items(), key=lambda x: -x[1])[:10]
        ])
        fig3 = px.bar(sub_df, x="Searches", y="Subreddit", orientation="h")
        fig3.update_layout(margin=dict(t=20, b=20, l=10, r=10), height=300, yaxis_title="")
        st.plotly_chart(fig3, use_container_width=True)

    st.markdown("---")
    st.subheader("Recent Activity")
    if stats["recent_jobs"]:
        activity_df = pd.DataFrame([
            {
                "Time": j.get("timestamp", "")[:19].replace("T", " "),
                "Type": j.get("type", "").upper(),
                "Details": (
                    f"r/{', '.join(j.get('subreddits', []))}" if j["type"] == "search"
                    else j.get("post_title", j.get("video_path", ""))[:60]
                ),
                "Platform": j.get("platform", "—"),
            }
            for j in stats["recent_jobs"]
        ])
        st.dataframe(activity_df, use_container_width=True, hide_index=True)
    else:
        st.caption("No activity yet. Start by searching Reddit!")

    if stats.get("all_videos"):
        st.markdown("---")
        st.subheader("All Videos")
        vdf = pd.DataFrame([
            {
                "Title": v.get("post_title", "")[:50],
                "Platform": v.get("platform", ""),
                "Genre": v.get("genre", ""),
                "Duration": f"{v.get('duration_sec', 0):.0f}s",
                "Size": f"{v.get('file_size_mb', 0):.1f}MB",
                "Images": v.get("num_images", 0),
                "Published": "✅" if v.get("published") else "—",
                "Created": v.get("timestamp", "")[:10],
            }
            for v in stats["all_videos"]
        ])
        st.dataframe(vdf, use_container_width=True, hide_index=True)

    if st.button("🗑️ Clear Analytics Data"):
        if (Path(__file__).parent / "data" / "analytics.json").exists():
            os.remove(Path(__file__).parent / "data" / "analytics.json")
            st.success("Analytics data cleared.")
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 0 — PIPELINE RUNNER
# ══════════════════════════════════════════════════════════════════════════════
elif page == "⚡ Pipeline Runner":
    st.header("⚡ Pipeline Runner")
    st.caption("Configure which steps to run, hit ▶ Run, and watch live granular progress for every stage.")

    # ── Step toggles ──────────────────────────────────────────────────────────
    st.subheader("Steps to run")
    c1, c2, c3, c4, c5 = st.columns(5)
    run_search   = c1.toggle("1 · Search Reddit",  value=True)
    run_script   = c2.toggle("2 · Script",          value=True,  disabled=not run_search)
    run_voice    = c3.toggle("3 · Voiceover",        value=True,  disabled=not run_script)
    run_images   = c4.toggle("4 · Images",           value=True,  disabled=not run_script)
    run_video    = c5.toggle("5 · Assemble Video",   value=True,  disabled=not (run_voice and run_images))

    st.markdown("---")

    # ── Step 1 config: Reddit ─────────────────────────────────────────────────
    if run_search:
        st.subheader("1 · Reddit Search")
        col_a, col_b, col_c = st.columns([3, 1, 1])
        with col_a:
            pr_subreddits = st.text_input("Subreddit(s)", placeholder="worldnews, AskReddit", key="pr_subs")
        with col_b:
            pr_sort = st.selectbox("Sort", ["Top", "Hot"], key="pr_sort")
        with col_c:
            pr_time = st.selectbox("Time", ["day", "week", "month", "year", "all"], index=1,
                                   key="pr_time", disabled=(pr_sort == "Hot"))
        col_d, col_e = st.columns(2)
        with col_d:
            pr_limit  = st.slider("Max posts", 1, 25, 5, key="pr_limit")
        with col_e:
            pr_min_score = st.number_input("Min score", 0, value=0, step=100, key="pr_min_score")
        pr_pick = st.selectbox("Which post to use", ["#1 (highest score)", "#2", "#3", "#4", "#5",
                                                      "Let me pick after search"], key="pr_pick")

    # ── Step 2 config: Script ─────────────────────────────────────────────────
    if run_script:
        st.markdown("---")
        st.subheader("2 · Script")
        col_p, col_g = st.columns(2)
        with col_p:
            pr_preset = st.selectbox("Platform Preset", list(PRESETS.keys()), key="pr_preset")
        with col_g:
            pr_genre = st.selectbox("Genre", [
                "Informative / Educational", "Entertaining / Funny",
                "Shocking / Controversial", "Heartwarming / Inspirational",
                "News / Current Events", "Opinion / Commentary",
                "Story Time / Narrative", "Mystery / Suspense",
            ], key="pr_genre")

        if pr_preset == "Custom":
            pr_duration  = st.slider("Duration (s)", 15, 600, 90, key="pr_dur")
            pr_style     = st.text_input("Style notes", key="pr_style")
        else:
            _p = PRESETS[pr_preset]
            st.caption(f"⏱️ {_p['duration_sec']}s · ~{_p['word_count']} words · {_p['aspect_ratio']} · {_p['platform']}")
            pr_duration, pr_style = _p["duration_sec"], ""

        col_prov, col_mod = st.columns(2)
        with col_prov:
            pr_provider_label = st.selectbox("AI Provider", list(PROVIDERS.keys()), key="pr_prov")
            pr_provider_key   = PROVIDERS[pr_provider_label]
        with col_mod:
            if pr_provider_key == "openai_replit":
                pr_model = st.selectbox("Model", OPENAI_REPLIT_MODELS, index=1, key="pr_model_oa")
            elif pr_provider_key == "openrouter_replit":
                pr_model = st.selectbox("Model", OPENROUTER_MODELS, key="pr_model_or")
            else:
                pr_model = st.text_input("Model name", "llama3.3", key="pr_model_ol")

        pr_ollama_url = pr_ollama_key = ""
        if pr_provider_key == "ollama_cloud":
            pr_ollama_url = st.text_input("Ollama Cloud base URL",
                                          value=os.environ.get("OLLAMA_CLOUD_BASE_URL", ""),
                                          placeholder="https://your-host/v1", key="pr_ol_url")
            pr_ollama_key = st.text_input("API key (optional)", type="password",
                                          value=os.environ.get("OLLAMA_CLOUD_API_KEY", ""), key="pr_ol_key")

    # ── Step 3 config: Voiceover ──────────────────────────────────────────────
    if run_voice:
        st.markdown("---")
        st.subheader("3 · Voiceover")
        col_l, col_s2 = st.columns(2)
        with col_l:
            pr_lang  = st.selectbox("Language", list(GTTS_LANGUAGES.keys()), key="pr_lang")
        with col_s2:
            pr_speed = st.selectbox("Speed", ["Normal", "Slow"], key="pr_speed")

    # ── Step 4 config: Images ─────────────────────────────────────────────────
    if run_images:
        st.markdown("---")
        st.subheader("4 · Images")
        col_i1, col_i2 = st.columns(2)
        with col_i1:
            pr_use_stock = st.toggle("Use stock photos", value=True, key="pr_stock")
        with col_i2:
            pr_aspect = st.selectbox("Aspect ratio", ["16:9", "9:16", "1:1", "4:3"], key="pr_aspect")
        if not os.environ.get("UNSPLASH_ACCESS_KEY") and not os.environ.get("PEXELS_API_KEY"):
            st.caption("No stock photo API key set — stylized placeholders will be used.")

    # ── Step 5 config: Video ──────────────────────────────────────────────────
    if run_video:
        st.markdown("---")
        st.subheader("5 · Video Assembly")
        col_v1, col_v2, col_v3 = st.columns(3)
        with col_v1:
            pr_ken_burns  = st.toggle("Ken Burns effect", value=True, key="pr_kb")
        with col_v2:
            pr_fps        = st.selectbox("FPS", [24, 30, 60], index=1, key="pr_fps")
        with col_v3:
            pr_transition = st.slider("Transition (s)", 0.0, 2.0, 0.5, 0.1, key="pr_trans")

    st.markdown("---")

    # ── Determine active steps ─────────────────────────────────────────────────
    last_steps = []
    if run_search:  last_steps.append("Reddit search")
    if run_script:  last_steps.append("script")
    if run_voice:   last_steps.append("voiceover")
    if run_images:  last_steps.append("images")
    if run_video:   last_steps.append("video assembly")
    run_label = " → ".join(last_steps) if last_steps else "nothing"

    # ── Visual pipeline map (always visible) ───────────────────────────────────
    STEP_DEFS = [
        ("🔍", "Search Reddit", run_search),
        ("✍️", "Script",        run_script),
        ("🎙️", "Voiceover",     run_voice),
        ("🖼️", "Images",        run_images),
        ("🎥", "Video",         run_video),
    ]

    map_cols = st.columns(len(STEP_DEFS))
    for col, (icon, label, enabled) in zip(map_cols, STEP_DEFS):
        if enabled:
            col.markdown(f"**{icon} {label}**")
        else:
            col.markdown(f"~~{icon} {label}~~")

    st.markdown("---")

    btn_label = f"▶  Run pipeline  ({run_label})"
    if not last_steps:
        st.warning("Enable at least one step above.")
    elif st.button(btn_label, type="primary", use_container_width=True):

        run_ok    = True
        timings   = {}          # step_name → elapsed seconds
        pipeline_start = time.time()

        # ── Overall progress bar (stays at top) ────────────────────────────────
        total_steps  = len(last_steps)
        overall_bar  = st.progress(0, text="Starting pipeline…")

        def _bar(n: int, label: str):
            overall_bar.progress(n / total_steps,
                                 text=f"Step {n}/{total_steps} — {label}")

        # ══ STEP 1 — REDDIT SEARCH ════════════════════════════════════════════
        if run_search and run_ok:
            t0 = time.time()
            subs = [s.strip() for s in pr_subreddits.split(",") if s.strip()]

            _bar(1, "Searching Reddit…")
            with st.status("🔍  Step 1 — Search Reddit", expanded=True) as s1:
                if not subs:
                    st.error("Enter at least one subreddit.")
                    s1.update(label="❌  Step 1 — Search Reddit: no subreddit entered", state="error")
                    run_ok = False
                else:
                    st.write(f"**Target subreddit(s):** {', '.join('r/'+x for x in subs)}")
                    st.write(f"**Sort:** {pr_sort}  |  **Time window:** {pr_time if pr_sort == 'Top' else 'n/a (Hot)'}")
                    st.write(f"**Fetching up to {pr_limit} posts…**")
                    try:
                        # ── Test credentials first ───────────────────────────
                        st.write("Verifying Reddit API credentials…")
                        from src.reddit import get_reddit_client
                        try:
                            _rc = get_reddit_client()
                            _rc.user.me()   # lightweight auth check (read-only apps return None, not an exception)
                            st.write("✓ Reddit API connected")
                        except Exception as _auth_err:
                            # read-only PRAW returns None from user.me(), not an error
                            # so only fail here on a real exception
                            _auth_str = str(_auth_err)
                            if "401" in _auth_str or "403" in _auth_str or "invalid_grant" in _auth_str.lower():
                                st.error(f"Reddit credentials rejected: {_auth_str}")
                                s1.update(
                                    label=f"❌  Step 1 — Reddit auth failed: {_auth_str[:80]}",
                                    state="error", expanded=True,
                                )
                                run_ok = False

                        if run_ok:
                            if pr_sort == "Top":
                                raw_posts = fetch_top_posts(subs, pr_time, pr_limit, 0)
                            else:
                                raw_posts = fetch_hot_posts(subs, pr_limit)

                            errors   = [p for p in raw_posts if "error" in p]
                            all_posts = [p for p in raw_posts if "error" not in p]

                            for err in errors:
                                st.warning(f"⚠️ r/{err['subreddit']}: {err['error']}")

                            st.write(f"**Raw results:** {len(raw_posts)} total  |  {len(all_posts)} valid  |  {len(errors)} API errors")

                            # score filter
                            if pr_min_score > 0:
                                before = len(all_posts)
                                all_posts = [p for p in all_posts if p.get("score", 0) >= pr_min_score]
                                st.write(f"**Score filter ≥ {pr_min_score:,}:** {before} → {len(all_posts)} posts kept")

                            if not all_posts:
                                if errors:
                                    err_summary = errors[0]["error"]
                                    fail_msg    = f"Reddit API error — {err_summary[:100]}"
                                elif pr_min_score > 0:
                                    fail_msg = f"All posts filtered out by score ≥ {pr_min_score:,} — lower the threshold"
                                else:
                                    fail_msg = "No posts returned — check subreddit names"
                                st.error(fail_msg)
                                s1.update(label=f"❌  Step 1 — {fail_msg}", state="error", expanded=True)
                                run_ok = False
                        else:
                            # Sort & stats
                            all_posts.sort(key=lambda p: p.get("score", 0), reverse=True)
                            top_score  = all_posts[0]["score"]
                            avg_score  = sum(p["score"] for p in all_posts) // len(all_posts)
                            top_ratio  = all_posts[0]["upvote_ratio"]

                            st.write("**Top posts found:**")
                            for i, p in enumerate(all_posts[:5]):
                                st.markdown(
                                    f"&nbsp;&nbsp;`#{i+1}` **{p['title'][:70]}{'…' if len(p['title'])>70 else ''}**  "
                                    f"⬆️ {p['score']:,} · 💬 {p['num_comments']:,} · "
                                    f"r/{p['subreddit']}"
                                )

                            # pick
                            if pr_pick == "Let me pick after search":
                                st.info("Pausing — choose a post below, then re-run the pipeline.")
                                s1.update(label="⏸  Step 1 — Search Reddit: awaiting your selection", state="complete")
                                st.session_state.posts = all_posts
                                run_ok = False
                            else:
                                pick_idx = min(int(pr_pick[1]) - 1, len(all_posts) - 1)
                                post = all_posts[pick_idx]
                                st.session_state.selected_post = post
                                log_search(subs, pr_time if pr_sort == "Top" else "hot", len(all_posts))

                                st.markdown("---")
                                st.write(f"**Selected post (#{pick_idx+1}):**")
                                m1, m2, m3, m4 = st.columns(4)
                                m1.metric("Score",    f"{post['score']:,}")
                                m2.metric("Comments", f"{post['num_comments']:,}")
                                m3.metric("Ratio",    f"{post['upvote_ratio']:.0%}")
                                m4.metric("Awards",   post.get("awards", 0))
                                st.info(f"**{post['title']}**  \nr/{post['subreddit']} · by u/{post['author']}")
                                if post.get("selftext"):
                                    with st.expander("Post body preview"):
                                        st.caption(post["selftext"][:500])

                                elapsed = time.time() - t0
                                timings["search"] = elapsed
                                s1.update(
                                    label=f"✅  Step 1 — Search Reddit  ({elapsed:.1f}s)  ·  "
                                          f"Selected: \"{post['title'][:55]}{'…' if len(post['title'])>55 else ''}\"",
                                    state="complete", expanded=False,
                                )
                    except Exception as ex:
                        st.error(f"Reddit API error: {ex}")
                        s1.update(label=f"❌  Step 1 — Search Reddit: {ex}", state="error")
                        run_ok = False
        else:
            post = st.session_state.selected_post

        # ══ STEP 2 — SCRIPT GENERATION ════════════════════════════════════════
        if run_script and run_ok:
            t0 = time.time()
            step_n = sum([run_search]) + 1
            _bar(step_n, "Generating script…")

            with st.status("✍️  Step 2 — Script Generation", expanded=True) as s2:
                st.write(f"**Post:** {post['title'][:80]}")
                st.write(f"**Platform preset:** {pr_preset}  |  **Genre:** {pr_genre}")
                st.write(f"**Provider:** {pr_provider_label}  |  **Model:** {pr_model}")
                st.write(f"**Target duration:** {pr_duration}s  (~{PRESETS.get(pr_preset, PRESETS['Custom'])['word_count']} words)")
                st.write("Sending prompt to AI model…")
                try:
                    script_result = generate_script(
                        post=post,
                        preset_name=pr_preset,
                        genre=pr_genre,
                        custom_duration=pr_duration,
                        custom_style=pr_style,
                        provider=pr_provider_key,
                        model=pr_model,
                        ollama_base_url=pr_ollama_url,
                        ollama_api_key=pr_ollama_key,
                    )
                    st.session_state.script = script_result
                    log_script(post["title"], script_result["platform"], pr_genre, script_result["estimated_word_count"])

                    wc   = script_result["estimated_word_count"]
                    wpm  = 130  # avg speaking pace
                    est  = round(wc / wpm * 60)

                    st.markdown("---")
                    sw1, sw2, sw3, sw4 = st.columns(4)
                    sw1.metric("Word count",    wc)
                    sw2.metric("Est. duration", f"{est}s")
                    sw3.metric("Target",        f"{pr_duration}s")
                    sw4.metric("Image prompts", len(script_result.get("image_prompts", [])))

                    with st.expander("📄 Full script", expanded=False):
                        st.markdown(f"**🪝 Hook**\n\n{script_result['hook']}")
                        st.markdown("---")
                        st.markdown(f"**📝 Main Script**\n\n{script_result['main_script']}")
                        st.markdown("---")
                        st.markdown(f"**📣 CTA**\n\n{script_result['cta']}")

                    with st.expander("🖼️ Image prompts", expanded=False):
                        for j, p_txt in enumerate(script_result.get("image_prompts", []), 1):
                            st.markdown(f"**{j}.** {p_txt}")

                    elapsed = time.time() - t0
                    timings["script"] = elapsed
                    s2.update(
                        label=f"✅  Step 2 — Script  ({elapsed:.1f}s)  ·  "
                              f"{wc} words  ·  {script_result['provider']} / {script_result['model']}",
                        state="complete", expanded=False,
                    )
                except Exception as ex:
                    st.error(f"Script generation error: {ex}")
                    s2.update(label=f"❌  Step 2 — Script: {ex}", state="error")
                    run_ok = False
        else:
            script_result = st.session_state.script

        # ══ STEP 3 — VOICEOVER ════════════════════════════════════════════════
        if run_voice and run_ok:
            t0 = time.time()
            step_n = sum([run_search, run_script]) + 1
            _bar(step_n, "Generating voiceover…")

            with st.status("🎙️  Step 3 — Voiceover", expanded=True) as s3:
                wc = len(script_result["full_script"].split())
                st.write(f"**Engine:** gTTS (free Google TTS)  |  **Language:** {pr_lang}  |  **Speed:** {pr_speed}")
                st.write(f"**Script length:** {wc} words")
                st.write("Sending text to TTS engine…")
                try:
                    voice_result = generate_voiceover(
                        script=script_result["full_script"],
                        language=pr_lang,
                        speed=pr_speed,
                    )
                    if "error" in voice_result:
                        st.error(voice_result["error"])
                        s3.update(label=f"❌  Step 3 — Voiceover: {voice_result['error']}", state="error")
                        run_ok = False
                    else:
                        st.session_state.voiceover = voice_result
                        dur   = voice_result["duration_sec"]
                        ratio = dur / max(script_result["target_duration_sec"], 1) * 100

                        st.markdown("---")
                        va, vb, vc = st.columns(3)
                        va.metric("Duration",     f"{dur:.1f}s")
                        vb.metric("Target",       f"{script_result['target_duration_sec']}s")
                        vc.metric("Match",        f"{ratio:.0f}%", delta=f"{dur - script_result['target_duration_sec']:.1f}s")

                        st.write("**Audio preview:**")
                        if os.path.exists(voice_result["path"]):
                            with open(voice_result["path"], "rb") as af:
                                st.audio(af.read(), format="audio/mp3")

                        elapsed = time.time() - t0
                        timings["voiceover"] = elapsed
                        s3.update(
                            label=f"✅  Step 3 — Voiceover  ({elapsed:.1f}s)  ·  {dur:.1f}s audio  ·  {pr_lang}",
                            state="complete", expanded=False,
                        )
                except Exception as ex:
                    st.error(f"Voiceover error: {ex}")
                    s3.update(label=f"❌  Step 3 — Voiceover: {ex}", state="error")
                    run_ok = False
        else:
            voice_result = st.session_state.voiceover

        # ══ STEP 4 — IMAGES ══════════════════════════════════════════════════
        if run_images and run_ok:
            t0 = time.time()
            step_n = sum([run_search, run_script, run_voice]) + 1
            prompts = script_result.get("image_prompts", []) or [post.get("title", "abstract background")]
            _bar(step_n, f"Fetching {len(prompts)} images…")

            with st.status(f"🖼️  Step 4 — Images  ({len(prompts)} slides)", expanded=True) as s4:
                stock_label = "Unsplash/Pexels stock" if (
                    os.environ.get("UNSPLASH_ACCESS_KEY") or os.environ.get("PEXELS_API_KEY")
                ) else "stylized placeholder (no stock key set)"
                st.write(f"**Source:** {stock_label if pr_use_stock else 'stylized placeholders'}")
                st.write(f"**Aspect ratio:** {pr_aspect}  |  **Slides:** {len(prompts)}")
                st.markdown("---")
                st.write("**Image prompts:**")
                for j, p_txt in enumerate(prompts, 1):
                    st.markdown(f"&nbsp;&nbsp;`{j}` {p_txt}")
                st.markdown("---")
                st.write("Fetching images…")

                try:
                    image_paths = prepare_images_for_video(
                        prompts, use_stock=pr_use_stock, aspect_ratio=pr_aspect
                    )
                    st.session_state.images = image_paths

                    st.write(f"**{len(image_paths)} images ready.** Preview:")
                    n_cols = min(len(image_paths), 4)
                    img_cols = st.columns(n_cols)
                    for i, img_p in enumerate(image_paths):
                        if os.path.exists(img_p):
                            img_cols[i % n_cols].image(
                                img_p,
                                caption=f"Slide {i+1}",
                                use_container_width=True,
                            )

                    elapsed = time.time() - t0
                    timings["images"] = elapsed
                    s4.update(
                        label=f"✅  Step 4 — Images  ({elapsed:.1f}s)  ·  {len(image_paths)} slides  ·  {pr_aspect}",
                        state="complete", expanded=False,
                    )
                except Exception as ex:
                    st.error(f"Image fetch error: {ex}")
                    s4.update(label=f"❌  Step 4 — Images: {ex}", state="error")
                    run_ok = False
        else:
            image_paths = st.session_state.images

        # ══ STEP 5 — VIDEO ASSEMBLY ═══════════════════════════════════════════
        if run_video and run_ok:
            t0 = time.time()
            step_n = sum([run_search, run_script, run_voice, run_images]) + 1
            _bar(step_n, "Assembling video with FFmpeg…")

            aspect_to_use = (pr_aspect if run_images
                             else script_result.get("aspect_ratio", "16:9"))
            safe_title = "".join(
                c if c.isalnum() or c in "-_" else "_"
                for c in post.get("title", "video")[:40]
            )
            out_filename = f"{safe_title}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"

            with st.status("🎥  Step 5 — Video Assembly", expanded=True) as s5:
                st.write(f"**Slides:** {len(image_paths)}  |  **Audio:** {voice_result['duration_sec']:.1f}s")
                st.write(f"**Resolution:** {aspect_to_use}  |  **FPS:** {pr_fps}  |  **Ken Burns:** {pr_ken_burns}")
                st.write(f"**Transition:** {pr_transition}s between slides")

                per_slide = voice_result["duration_sec"] / max(len(image_paths), 1)
                st.write(f"**Estimated time per slide:** {per_slide:.1f}s")
                st.markdown("---")
                st.write("⚙️  Running FFmpeg — this takes 1–3 minutes…")
                prog_msg = st.empty()
                prog_msg.info("FFmpeg encoding in progress…")

                try:
                    video_result = assemble_video(
                        image_paths=image_paths,
                        audio_path=voice_result["path"],
                        output_filename=out_filename,
                        aspect_ratio=aspect_to_use,
                        ken_burns=pr_ken_burns,
                        transition_duration=pr_transition,
                        fps=pr_fps,
                    )
                    prog_msg.empty()

                    if "error" in video_result:
                        st.error(video_result["error"])
                        s5.update(label=f"❌  Step 5 — Video: {video_result['error'][:80]}", state="error")
                        run_ok = False
                    else:
                        st.session_state.video = video_result
                        log_video(
                            post_title=post.get("title", ""),
                            platform=script_result["platform"],
                            genre=pr_genre,
                            duration_sec=video_result["duration_sec"],
                            file_size_mb=video_result["file_size_mb"],
                            video_path=video_result["path"],
                            audio_path=voice_result["path"],
                            num_images=len(image_paths),
                        )
                        st.markdown("---")
                        va, vb, vc, vd = st.columns(4)
                        va.metric("Duration",   f"{video_result['duration_sec']:.1f}s")
                        vb.metric("File size",  f"{video_result['file_size_mb']} MB")
                        vc.metric("Resolution", video_result["resolution"])
                        vd.metric("FPS",        pr_fps)

                        st.write("**Video preview:**")
                        vpath = video_result["path"]
                        if os.path.exists(vpath):
                            with open(vpath, "rb") as vf:
                                vbytes = vf.read()
                            st.video(vbytes)
                            st.download_button(
                                "⬇️  Download MP4",
                                data=vbytes,
                                file_name=video_result["filename"],
                                mime="video/mp4",
                                use_container_width=True,
                            )

                        elapsed = time.time() - t0
                        timings["video"] = elapsed
                        s5.update(
                            label=f"✅  Step 5 — Video  ({elapsed:.1f}s)  ·  "
                                  f"{video_result['duration_sec']:.1f}s  ·  "
                                  f"{video_result['file_size_mb']} MB  ·  {video_result['resolution']}",
                            state="complete", expanded=False,
                        )
                except Exception as ex:
                    st.error(f"Video assembly error: {ex}")
                    s5.update(label=f"❌  Step 5 — Video: {ex}", state="error")
                    run_ok = False

        # ══ FINAL SUMMARY ════════════════════════════════════════════════════
        if run_ok and last_steps:
            overall_bar.progress(1.0, text="Pipeline complete!")
            total_elapsed = time.time() - pipeline_start

            st.markdown("---")
            st.subheader("🏁 Pipeline Summary")

            # timing table
            timing_rows = []
            step_map_labels = {
                "search":    "🔍 Search Reddit",
                "script":    "✍️ Script",
                "voiceover": "🎙️ Voiceover",
                "images":    "🖼️ Images",
                "video":     "🎥 Video Assembly",
            }
            for key, label in step_map_labels.items():
                if key in timings:
                    timing_rows.append({"Step": label, "Time": f"{timings[key]:.1f}s",
                                        "Share": f"{timings[key]/total_elapsed*100:.0f}%"})

            if timing_rows:
                sum_cols = st.columns(len(timing_rows) + 1)
                for i, row in enumerate(timing_rows):
                    sum_cols[i].metric(row["Step"], row["Time"])
                sum_cols[-1].metric("⏱️ Total", f"{total_elapsed:.1f}s")

            # waterfall chart
            if len(timing_rows) > 1:
                fig = px.bar(
                    pd.DataFrame(timing_rows),
                    x="Time", y="Step", orientation="h",
                    title="Time per step",
                    text="Time",
                    color="Step",
                )
                fig.update_layout(showlegend=False, height=250,
                                  margin=dict(t=40, b=10, l=10, r=10))
                st.plotly_chart(fig, use_container_width=True)

            st.success(
                f"All {len(last_steps)} step(s) completed successfully in **{total_elapsed:.1f}s**. "
                f"Results are loaded into each individual step page for further editing."
            )
