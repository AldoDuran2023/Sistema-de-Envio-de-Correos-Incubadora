import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app
from .models import db, Participacion, Participante, Notificacion
import time

def send_email(to_email, subject, body):
    # (Tu código de envío de email se mantiene igual)
    try:
        msg = MIMEMultipart()
        msg['From'] = current_app.config['MAIL_DEFAULT_SENDER']
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))

        server = smtplib.SMTP(current_app.config['MAIL_SERVER'], current_app.config['MAIL_PORT'])
        server.starttls()
        server.login(current_app.config['MAIL_USERNAME'], current_app.config['MAIL_PASSWORD'])
        text = msg.as_string()
        server.sendmail(current_app.config['MAIL_DEFAULT_SENDER'], to_email, text)
        server.quit()
        return True, None
    except Exception as e:
        return False, str(e)

def get_pending_notifications(event_id, limit=32):
    """
    Obtiene participantes que:
    1. Tienen certificado 'Impreso'.
    2. NO han recogido el certificado (estado != 'ENTREGADO').
    3. NO han sido notificados exitosamente antes.
    4. Tienen email válido.
    """
    
    # Subquery: IDs que ya tienen notificación 'Enviado'
    sent_subquery = db.session.query(Notificacion.participacion_id).filter(
        Notificacion.estado == 'Enviado'
    ).subquery()

    pending = db.session.query(Participacion).join(Participante).filter(
        Participacion.evento_id == event_id,
        Participacion.estado_certificado == 'Impreso',   # Solo si ya está impreso
        Participacion.estado != 'ENTREGADO',     # <--- LOGICA CLAVE: Si ya lo recogió, no notificar
        ~Participacion.id.in_(sent_subquery),            # Que no se le haya enviado antes
        Participante.email.isnot(None),
        Participante.email != ''
    ).limit(limit).all()
    
    return pending

def process_notifications(event_id):
    pending_participations = get_pending_notifications(event_id, limit=32)
    results = {'total': len(pending_participations), 'success': 0, 'failed': 0, 'errors': []}

    if not pending_participations:
        return results

    for p in pending_participations:
        participante = p.participante
        evento = p.evento
        
        subject = f"Certificado Listo - {evento.nombre_evento}"
        # Se recomienda mover el HTML a un template file, pero por ahora inline está bien
        body = f"""<html><body>
            <p>Hola <strong>{participante.nombre_normalizado}</strong>,</p>
            <p>Tu certificado del evento <strong>{evento.nombre_evento}</strong> está listo.</p>
            <p>Por favor acércate a recogerlo.</p>
        </body></html>"""
        
        success, error = send_email(participante.email, subject, body)
        
        estado_notif = 'Enviado' if success else 'Fallido'
        
        notificacion = Notificacion(
            participacion_id=p.id,
            canal='Email',
            estado=estado_notif,
            mensaje_error=error,
            veces_notificado=1
        )
        db.session.add(notificacion)
        
        if success:
            results['success'] += 1
        else:
            results['failed'] += 1
            results['errors'].append(f"{participante.email}: {error}")
            
        time.sleep(1) # Pausa cortés al servidor SMTP

    db.session.commit()
    return results