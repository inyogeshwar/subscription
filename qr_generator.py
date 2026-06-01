import qrcode
from io import BytesIO

def generate_upi_qr(upi_id, amount, label="Subscription"):
    """
    Generates a UPI payment standard standard format QR Image stream
    """
    amount_str = f"{float(amount):.2f}"
    payload = f"upi://pay?pa={upi_id}&pn=PremiumMembership&am={amount_str}&cu=INR&tn={label}"
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    bio = BytesIO()
    img.save(bio, 'PNG')
    bio.seek(0)
    return bio
