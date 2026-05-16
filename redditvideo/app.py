import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
from datetime import datetime

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
        ["🔍 Search Reddit", "✍️ Script Generator", "🎙️ Voiceover", "🖼️ Images", "🎥 Assemble Video", "📊 Analytics"],
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
