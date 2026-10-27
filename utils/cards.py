import streamlit as st


def kpi_card(title, value, delta=None):

    with st.container(border=True):

        st.markdown(f"#### {title}")

        st.markdown(
            f"<h2 style='color:#E8772E'>{value}</h2>",
            unsafe_allow_html=True
        )

        if delta is not None:
            st.caption(delta)