
import streamlit as st
from datetime import date, time
from services.lottery_upload_service import process_lottery_result_upload


MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

ALLOWED_FILE_TYPES = ["pdf", "jpg", "jpeg", "png"]


def is_valid_file(file_name, file_bytes):
    """
    Validate the file extension and basic file signature.
    """

    extension = file_name.rsplit(".", 1)[-1].lower()

    if extension not in ALLOWED_FILE_TYPES:
        return False

    if extension == "pdf":
        return file_bytes.startswith(b"%PDF-")

    if extension in ("jpg", "jpeg"):
        return file_bytes.startswith(b"\xff\xd8\xff")

    if extension == "png":
        return file_bytes.startswith(
            b"\x89PNG\r\n\x1a\n"
        )

    return False


def show_pdf_upload():

    st.subheader("📤 Upload Lottery Result")

    st.info(
        "Upload lottery results in PDF, JPG, JPEG "
        "or PNG format with the correct date and draw time."
    )

    with st.form("lottery_result_upload_form"):

        lottery_name = st.text_input(
            "Lottery Name",
            placeholder="Example: Dear Lottery"
        )

        result_date = st.date_input(
            "Result Date",
            value=date.today()
        )

        draw_time = st.selectbox(
            "Draw Time",
            options=[
                "01:00 PM",
                "06:00 PM",
                "08:00 PM"
            ]
        )

        result_file = st.file_uploader(
            "Select Lottery Result (PDF / JPG / JPEG / PNG)",
            type=ALLOWED_FILE_TYPES,
            help="Maximum file size: 10 MB"
        )

        submitted = st.form_submit_button(
            "📤 Upload Result"
        )

    if submitted:

        # Validate lottery name
        lottery_name = lottery_name.strip()

        if not lottery_name:
            st.error("Please enter lottery name.")
            return

        # Validate file selection
        if result_file is None:
            st.error("Please select a result file.")
            return

        # Validate file size
        if result_file.size > MAX_FILE_SIZE:
            st.error("File size must not exceed 10 MB.")
            return

        if result_file.size == 0:
            st.error("Uploaded file is empty.")
            return

        # Read uploaded file
        file_bytes = result_file.getvalue()

        # Validate file format
        if not is_valid_file(
            result_file.name,
            file_bytes
        ):
            st.error(
                "Invalid file format. Please upload "
                "a valid PDF, JPG, JPEG or PNG file."
            )
            return

        # Convert selected draw time
        selected_time = {
            "01:00 PM": time(13, 0),
            "06:00 PM": time(18, 0),
            "08:00 PM": time(20, 0)
        }

        draw_time_value = selected_time[draw_time]

        # Display validation result
        
        # Get authenticated admin client
        admin_client = st.session_state.get("admin_client")

        if admin_client is None:
            st.error("Admin session missing. Please login again.")
            return

        try:
            with st.spinner("Uploading lottery result..."):

                upload_result = process_lottery_result_upload(
                    admin_client=admin_client,
                    lottery_name=lottery_name,
                    result_date=result_date,
                    draw_time=draw_time_value,
                    file_name=result_file.name,
                    file_bytes=file_bytes
                )

            st.success(
                "Lottery result uploaded successfully!"
            )

            st.write(
                "Lottery:",
                lottery_name
            )

            st.write(
                "Result Date:",
                result_date
            )

            st.write(
                "Draw Time:",
                draw_time_value.strftime("%I:%M %p")
            )

            st.write(
                "File Name:",
                result_file.name
            )

            st.write(
                "Draw ID:",
                upload_result["draw_id"]
            )

            st.info(
                "Result saved with pending status. "
                "Verification and publication will "
                "be implemented in the next phase."
            )

        except Exception as error:
            st.error(f"Upload failed: {error}")
