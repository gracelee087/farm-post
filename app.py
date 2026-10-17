"""Farm Post: one photo + a short note -> sales listing (locally with Gemma)."""
import streamlit as st

import outbox
import publish_site
import publish_telegram

st.set_page_config(page_title="Farm Post", page_icon="🥕")

st.markdown("""
<style>
html, body, [class*="st-"], p, label, input, textarea { font-size: 1.4rem !important; }
h1 { font-size: 2.6rem !important; }
.stButton button { width: 100%; font-size: 1.7rem !important; padding: 1rem; }
</style>
""", unsafe_allow_html=True)

st.title("Farm Post")
if "msg" in st.session_state:
    st.success(st.session_state.pop("msg"))


def publish_all(records):
    publish_site.publish(records)
    if publish_telegram.configured():
        publish_telegram.publish(records)


# Status + automatic publishing when online.
online = outbox.is_online()
if online:
    try:
        sent = outbox.flush(publish_all)
        if sent:
            st.success(f"{sent} listing(s) published.")
    except Exception as e:
        st.error(f"Publishing failed, will retry later: {e}")
waiting = len(outbox.pending())
channel = "Telegram + web page" if publish_telegram.configured() else "web page only (Telegram not set up)"
st.markdown(f"**{'🟢 Online' if online else '🔴 Offline'}** · {waiting} waiting · {channel}")
if st.button("Publish now", disabled=waiting == 0):
    if outbox.is_online():
        st.session_state.msg = f"{outbox.flush(publish_all)} listing(s) published."
        st.rerun()
    else:
        st.warning("No internet. Listings will be published automatically later.")

st.header("1. Photo")
camera = st.camera_input("Take a photo")
upload = st.file_uploader("…or choose a picture", type=["jpg", "jpeg", "png"])
photo = camera or upload

st.header("2. Note")
note = st.text_input("For example: 10 kg potatoes €12  ·  hand-knitted scarf, wool, $25")

if st.button("Create listing", type="primary", disabled=photo is None):
    try:
        from generate import generate_post
    except ImportError:
        st.error("Listing generator not found (generate.py).")
    else:
        with st.spinner("Writing the listing … please wait"):
            try:
                st.session_state.post = generate_post(photo.getvalue(), note)
                st.session_state.image = photo.getvalue()
            except Exception as e:
                st.error(f"Could not create the listing: {e}")

if "post" in st.session_state:
    post = st.session_state.post
    st.header("3. Check the listing")
    st.image(st.session_state.image)
    title = st.text_input("Title", post.get("title", ""))
    body = st.text_area("Description", post.get("body", ""), height=250)
    price = " · ".join(p for p in (post.get("price_text"), post.get("unit_price_text")) if p)
    if price:
        st.markdown(f"### Price: {price}")
    if st.button("Save"):
        outbox.save({**post, "title": title, "body": body}, st.session_state.image)
        del st.session_state.post, st.session_state.image
        st.session_state.msg = "Saved. It will be published as soon as there is internet."
        st.rerun()
