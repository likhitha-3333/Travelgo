from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import boto3
from boto3.dynamodb.conditions import Key, Attr
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from decimal import Decimal
import uuid
import random

app = Flask(__name__)
app.secret_key = 'e0d15ae2faa18025f4e2a0c7dc5a7b8a830791cc83ad7538667ce14ca2ad8bc0'  # Replace in production with env var

# AWS Setup
REGION = 'ap-south-1'
dynamodb = boto3.resource('dynamodb', region_name=REGION)
sns_client = boto3.client('sns', region_name=REGION)

users_table = dynamodb.Table('travelgo_users')
bookings_table = dynamodb.Table('bookings')
SNS_TOPIC_ARN = 'arn:aws:sns:ap-south-1:353250843450:TravelGoBookingTopic'

def send_sns_notification(subject, message):
    try:
        sns_client.publish(TopicArn=SNS_TOPIC_ARN, Subject=subject, Message=message)
    except Exception as e:
        print(f"SNS Error: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        pw = request.form['password']
        if users_table.get_item(Key={'email': email}).get('Item'):
            flash('Email already exists!', 'error')
            return render_template('register.html')
        users_table.put_item(Item={'email': email,
                                   'password': generate_password_hash(pw)})
        flash('Registered! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']; pw = request.form['password']
        itm = users_table.get_item(Key={'email': email}).get('Item')
        if itm and check_password_hash(itm['password'], pw):
            session['email'] = email
            flash('Logged in!', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid credentials', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('email', None)
    flash('Logged out', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))
    email = session['email']
    resp = bookings_table.query(
        KeyConditionExpression=Key('user_email').eq(email),
        ScanIndexForward=False
    )
    bookings = resp.get('Items', [])
    for b in bookings:
        if 'total_price' in b:
            b['total_price'] = float(b['total_price'])
    return render_template('dashboard.html', bookings=bookings)

# ------- TRAIN -------
@app.route('/train')
def train():
    if 'email' not in session: return redirect(url_for('login'))
    return render_template('train.html')

@app.route('/confirm_train_details')
def confirm_train_details():
    if 'email' not in session: return redirect(url_for('login'))
    bd = {
        'name': request.args.get('name'),
        'train_number': request.args.get('trainNumber'),
        'source': request.args.get('source'),
        'destination': request.args.get('destination'),
        'departure_time': request.args.get('departureTime'),
        'arrival_time': request.args.get('arrivalTime'),
        'price_per_person': Decimal(request.args.get('price')),
        'travel_date': request.args.get('date'),
        'num_persons': int(request.args.get('persons')),
        'item_id': request.args.get('trainId'),
        'booking_type': 'train',
        'user_email': session['email'],
    }
    bd['total_price'] = bd['price_per_person'] * bd['num_persons']
    resp = bookings_table.scan(
        FilterExpression=Attr('item_id').eq(bd['item_id']) &
                         Attr('travel_date').eq(bd['travel_date']) &
                         Attr('booking_type').eq('train')
    )
    booked = set()
    for b in resp.get('Items', []):
        if 'seats_display' in b:
            booked.update(b['seats_display'].split(', '))
    all_seats = [f"S{i}" for i in range(1,101)]
    avail = [s for s in all_seats if s not in booked]
    if len(avail) < bd['num_persons']:
        flash("Not enough seats", "error"); return redirect(url_for('train'))
    sample = random.sample(avail, bd['num_persons'])
    bd['proposed_seats_display'] = ', '.join(sample)
    session['pending_booking'] = bd
    return render_template('confirm_train_details.html', booking=bd, available_seats_display=sample)

@app.route('/final_confirm_train_booking', methods=['POST'])
def final_confirm_train_booking():
    if 'email' not in session: return jsonify({'success':False}),401
    bd = session.pop('pending_booking', None)
    if not bd: return jsonify({'success':False, 'message':'No pending'}),400
    resp = bookings_table.scan(
        FilterExpression=Attr('item_id').eq(bd['item_id']) &
                         Attr('travel_date').eq(bd['travel_date']) &
                         Attr('booking_type').eq('train')
    )
    booked = set()
    for b in resp.get('Items', []):
        if 'seats_display' in b:
            booked.update(b['seats_display'].split(', '))
    avail = [s for s in [f"S{i}" for i in range(1,101)] if s not in booked]
    if len(avail) < bd['num_persons']:
        return jsonify({'success':False, 'message':'Not enough seats'}),400
    alloc = random.sample(avail, bd['num_persons'])
    bd['seats_display'] = ', '.join(alloc)
    bd['booking_id'] = str(uuid.uuid4())
    bd['booking_date'] = datetime.now().isoformat()
    bookings_table.put_item(Item=bd)
    send_sns_notification("Train Booking Confirmed",
        f"Train {bd['train_number']} on {bd['travel_date']}, seats {bd['seats_display']}, total ₹{bd['total_price']}")
    return jsonify({'success':True, 'redirect': url_for('dashboard')}),200

# ------- BUS -------
@app.route('/bus')
def bus():
    if 'email' not in session: return redirect(url_for('login'))
    return render_template('bus.html')

@app.route('/confirm_bus_details')
def confirm_bus_details():
    if 'email' not in session: return redirect(url_for('login'))
    bd = {
        'name': request.args.get('name'),
        'source': request.args.get('source'),
        'destination': request.args.get('destination'),
        'time': request.args.get('time'),
        'type': request.args.get('type'),
        'price_per_person': Decimal(request.args.get('price')),
        'travel_date': request.args.get('date'),
        'num_persons': int(request.args.get('persons')),
        'item_id': request.args.get('busId'),
        'booking_type': 'bus',
        'user_email': session['email'],
    }
    bd['total_price'] = bd['price_per_person'] * bd['num_persons']
    session['pending_booking'] = bd
    return redirect(url_for('select_bus_seats',
                            name=bd['name'], source=bd['source'], destination=bd['destination'],
                            time=bd['time'], type=bd['type'], price=str(bd['price_per_person']),
                            date=bd['travel_date'], persons=str(bd['num_persons']), busId=bd['item_id']))

@app.route('/select_bus_seats')
def select_bus_seats():
    if 'email' not in session: return redirect(url_for('login'))
    bd = session.get('pending_booking') or {}
    resp = bookings_table.scan(
        FilterExpression=Attr('item_id').eq(bd['item_id']) &
                         Attr('travel_date').eq(bd['travel_date']) &
                         Attr('booking_type').eq('bus')
    )
    booked = set()
    for b in resp.get('Items', []):
        if 'seats_display' in b:
            booked.update(b['seats_display'].split(', '))
    all_seats = [f"S{i}" for i in range(1,41)]
    return render_template('select_bus_seats.html', booking=bd, booked_seats=booked, all_seats=all_seats)

@app.route('/final_confirm_bus_booking', methods=['POST'])
def final_confirm_bus_booking():
    if 'email' not in session: return redirect(url_for('login'))
    bd = session.pop('pending_booking', None)
    seats = request.form.get('selected_seats')
    if not bd or not seats:
        flash("Missing data", "error"); return redirect(url_for('bus'))
    sel = seats.split(', ')
    resp = bookings_table.scan(
        FilterExpression=Attr('item_id').eq(bd['item_id']) &
                         Attr('travel_date').eq(bd['travel_date']) &
                         Attr('booking_type').eq('bus')
    )
    booked = set()
    for b in resp.get('Items', []):
        if 'seats_display' in b:
            booked.update(b['seats_display'].split(', '))
    if any(s in booked for s in sel):
        flash("Seats taken", "error")
        session['pending_booking'] = bd
        return redirect(url_for('select_bus_seats', **request.form))
    bd['seats_display'] = seats
    bd['booking_id'] = str(uuid.uuid4())
    bd['booking_date'] = datetime.now().isoformat()
    bookings_table.put_item(Item=bd)
    send_sns_notification("Bus Booking Confirmed",
        f"Bus on {bd['travel_date']} at {bd['time']}, seats {seats}, ₹{bd['total_price']}")
    flash("Booked!", "success")
    return redirect(url_for('dashboard'))

# ------- FLIGHT -------
@app.route('/flight')
def flight():
    if 'email' not in session: return redirect(url_for('login'))
    return render_template('flight.html')

@app.route('/confirm_flight_details')
def confirm_flight_details():
    if 'email' not in session: return redirect(url_for('login'))
    bd = {
        'flight_id': request.args['flight_id'],
        'airline': request.args['airline'],
        'flight_number': request.args['flight_number'],
        'source': request.args['source'],
        'destination': request.args['destination'],
        'departure_time': request.args['departure'],
        'arrival_time': request.args['arrival'],
        'travel_date': request.args['date'],
        'num_persons': int(request.args['passengers']),
        'price_per_person': Decimal(request.args['price']),
        'booking_type': 'flight',
        'user_email': session['email'],
    }
    bd['total_price'] = bd['price_per_person'] * bd['num_persons']
    session['pending_booking'] = bd
    return render_template('confirm_flight_details.html', booking=bd)

@app.route('/confirm_flight_booking', methods=['POST'])
def confirm_flight_booking():
    if 'email' not in session: return redirect(url_for('login'))
    bd = session.pop('pending_booking', None)
    if not bd:
        flash("No pending", "error"); return redirect(url_for('flight'))
    bd['booking_id'] = str(uuid.uuid4())
    bd['booking_date'] = datetime.now().isoformat()
    bookings_table.put_item(Item=bd)
    send_sns_notification("Flight Booking Confirmed",
        f"{bd['airline']} {bd['flight_number']} on {bd['travel_date']}, ₹{bd['total_price']}")
    flash("Flight booked!", "success")
    return redirect(url_for('dashboard'))

# ------- HOTEL -------
@app.route('/hotel')
def hotel():
    if 'email' not in session: return redirect(url_for('login'))
    return render_template('hotel.html')

@app.route('/confirm_hotel_details')
def confirm_hotel_details():
    if 'email' not in session: return redirect(url_for('login'))
    bd = {
        'name': request.args.get('name'),
        'location': request.args.get('location'),
        'checkin_date': request.args.get('checkin'),
        'checkout_date': request.args.get('checkout'),
        'num_rooms': int(request.args.get('rooms')),
        'num_guests': int(request.args.get('guests')),
        'price_per_night': Decimal(request.args.get('price')),
        'rating': int(request.args.get('rating')),
        'booking_type': 'hotel',
        'user_email': session['email'],
    }
    try:
        ci = datetime.fromisoformat(bd['checkin_date'])
        co = datetime.fromisoformat(bd['checkout_date'])
        nights = (co - ci).days
        if nights <= 0:
            flash("Invalid dates", "error"); return redirect(url_for('hotel'))
        bd['nights'] = nights
        bd['total_price'] = bd['price_per_night'] * bd['num_rooms'] * nights
    except ValueError:
        flash("Bad dates", "error"); return redirect(url_for('hotel'))
    session['pending_booking'] = bd
    return render_template('confirm_hotel_details.html', booking=bd)

@app.route('/confirm_hotel_booking', methods=['POST'])
def confirm_hotel_booking():
    if 'email' not in session: return redirect(url_for('login'))
    bd = session.pop('pending_booking', None)
    if not bd:
        flash("No pending", "error"); return redirect(url_for('hotel'))
    bd['booking_id'] = str(uuid.uuid4())
    bd['booking_date'] = datetime.now().isoformat()
    bookings_table.put_item(Item=bd)
    send_sns_notification("Hotel Booking Confirmed",
        f"{bd['name']} from {bd['checkin_date']} to {bd['checkout_date']}, ₹{bd['total_price']}")
    flash("Hotel booked!", "success")
    return redirect(url_for('dashboard'))

# ------- CANCEL -------
@app.route('/cancel_booking', methods=['POST'])
def cancel_booking():
    if 'email' not in session: return redirect(url_for('login'))
    bid = request.form.get('booking_id')
    bdate = request.form.get('booking_date')
    if not bid or not bdate:
        flash("Missing cancellation info", "error"); return redirect(url_for('dashboard'))
    bookings_table.delete_item(
        Key={'user_email': session['email'], 'booking_date': bdate}
    )
    flash(f"Cancelled {bid}", "success")
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
