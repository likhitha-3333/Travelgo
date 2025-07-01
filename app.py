from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import boto3
from boto3.dynamodb.conditions import Key, Attr
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from decimal import Decimal
import uuid
import random

app = Flask(_name_)
app.secret_key = 'e0d15ae2faa18025f4e2a0c7dc5a7b8a830791cc83ad7538667ce14ca2ad8bc0'  # IMPORTANT: Change this to a strong, random key in production!

# AWS Setup using IAM Role
REGION = 'us-east-1'  # Replace with your actual AWS region
dynamodb = boto3.resource('dynamodb', region_name=REGION)
sns_client = boto3.client('sns', region_name=REGION)

# DynamoDB Tables
users_table = dynamodb.Table('travelgo_users')
bookings_table = dynamodb.Table('bookings')

SNS_TOPIC_ARN = 'arn:aws:sns:us-east-1:713881794827:travelgo:302dcf42-b7bd-4797-bbbf-4f00cff92d6a'

# Function to send SNS notifications
def send_sns_notification(subject, message):
    try:
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject,
            Message=message
        )
        print(f"[✔] SNS notification sent: {subject}")
    except Exception as e:
        print(f"SNS Error: Could not send notification - {e}")

# Routes
@app.route('/')
def home():
    return render_template('index.html', logged_in='email' in session)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        name = request.form['name']
        password = request.form['password']
        
        # Check if user already exists
        existing = users_table.get_item(Key={'email': email})
        if 'Item' in existing:
            flash('User already exists!', 'error')
            return render_template('register.html')
        
        # Hash password and store user
        hashed_password = generate_password_hash(password)
        user_data = {
            'email': email,
            'name': name,
            'password': hashed_password,
            'logins': 0
        }
        
        users_table.put_item(Item=user_data)
        print(f"[✔] Registered new user: {email}")
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        # Retrieve user by email
        user_response = users_table.get_item(Key={'email': email})
        
        if 'Item' in user_response:
            user = user_response['Item']
            if check_password_hash(user['password'], password):
                session['email'] = email
                session['user_name'] = user.get('name', email)
                
                # Update login count
                users_table.update_item(
                    Key={'email': email},
                    UpdateExpression='ADD logins :val',
                    ExpressionAttributeValues={':val': 1}
                )
                
                flash('Login successful! Welcome back.', 'success')
                return redirect(url_for('dashboard'))
        
        flash('Invalid email or password. Please try again.', 'error')
        return render_template('login.html')
    
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))
    
    user_email = session['email']
    
    # Query bookings for the logged-in user
    try:
        response = bookings_table.query(
            KeyConditionExpression=Key('user_email').eq(user_email),
            ScanIndexForward=False  # Get most recent bookings first
        )
        bookings = response.get('Items', [])
        
        # Convert Decimal types from DynamoDB to float for display
        for booking in bookings:
            for key, value in booking.items():
                if isinstance(value, Decimal):
                    booking[key] = float(value)
                    
    except Exception as e:
        print(f"Error fetching bookings: {e}")
        bookings = []
    
    return render_template('dashboard.html', username=user_email, bookings=bookings)

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('home'))

# Booking Routes
@app.route('/bus')
def bus_booking():
    if 'email' not in session:
        flash('Please login to book tickets.', 'error')
        return redirect(url_for('login'))
    return render_template('bus.html')

@app.route('/train')
def train_booking():
    if 'email' not in session:
        flash('Please login to book tickets.', 'error')
        return redirect(url_for('login'))
    return render_template('train.html')

@app.route('/flight')
def flight_booking():
    if 'email' not in session:
        flash('Please login to book tickets.', 'error')
        return redirect(url_for('login'))
    return render_template('flight.html')

@app.route('/hotel')
def hotel_booking():
    if 'email' not in session:
        flash('Please login to book tickets.', 'error')
        return redirect(url_for('login'))
    return render_template('hotel.html')

# Bus Booking Flow
@app.route('/confirm_bus_details')
def confirm_bus_details():
    if 'email' not in session:
        return redirect(url_for('login'))

    booking_details = {
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
        'total_price': Decimal(request.args.get('price')) * int(request.args.get('persons'))
    }
    
    session['pending_booking'] = booking_details
    return render_template("bus.html", booking=booking_details)



@app.route('/api/book_bus', methods=['POST'])
def api_book_bus():
    if 'email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    booking_data = {
        'user_email': session['email'],
        'booking_type': 'bus',
        'booking_id': str(uuid.uuid4()),
        'booking_date': datetime.now().isoformat(),
        'name': data.get('busName'),
        'source': data.get('from'),
        'destination': data.get('to'),
        'travel_date': data.get('date'),
        'seats_display': data.get('seat'),
        'total_price': Decimal(str(data.get('price', 0))),
        'status': data.get('status', 'Confirmed')
    }

    try:
        bookings_table.put_item(Item=booking_data)
        
        # Send notification
        send_sns_notification(
            subject="Bus Booking Confirmed",
            message=f"Dear {booking_data['user_email']},\nYour bus booking is confirmed.\nSeats: {booking_data['seats_display']}\nTotal Price: ₹{booking_data['total_price']}"
        )
        
        return jsonify({'message': 'Bus booked successfully!'}), 200
    except Exception as e:
        print(f"Error booking bus: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/final_confirm_bus_booking', methods=['POST'])
def final_confirm_bus_booking():
    if 'email' not in session:
        return redirect(url_for('login'))

    booking = session.pop('pending_booking', None)
    selected_seats_str = request.form.get('selected_seats')
    
    if not booking or not selected_seats_str:
        flash("Booking failed! Missing data or session expired.", "error")
        return redirect(url_for("bus_booking"))

    selected_seats = selected_seats_str.split(', ')

    # Check seat availability
    try:
        response = bookings_table.scan(
            FilterExpression=Attr('item_id').eq(booking['item_id']) &
                             Attr('travel_date').eq(booking['travel_date']) &
                             Attr('booking_type').eq('bus')
        )
        
        existing_booked_seats = set()
        for b in response.get('Items', []):
            if 'seats_display' in b:
                existing_booked_seats.update(b['seats_display'].split(', '))

        if any(s in existing_booked_seats for s in selected_seats):
            flash("One or more selected seats are already booked. Please choose again.", "error")
            session['pending_booking'] = booking
            return redirect(url_for('select_bus_seats', 
                                    name=booking['name'],
                                    source=booking['source'],
                                    destination=booking['destination'],
                                    time=booking['time'],
                                    type=booking['type'],
                                    price=str(booking['price_per_person']),
                                    date=booking['travel_date'],
                                    persons=str(booking['num_persons']),
                                    busId=booking['item_id']))

        # Finalize booking
        booking['seats_display'] = selected_seats_str
        booking['booking_id'] = str(uuid.uuid4())
        booking['booking_date'] = datetime.now().isoformat()

        bookings_table.put_item(Item=booking)
        
        send_sns_notification(
            subject="Bus Booking Confirmed",
            message=f"Dear {booking['user_email']},\nYour bus from {booking['source']} to {booking['destination']} on {booking['travel_date']} is confirmed.\nSeats: {booking['seats_display']}\nTotal Price: ₹{booking['total_price']}"
        )

        flash('Bus booking confirmed successfully!', 'success')
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        print(f"Error confirming bus booking: {e}")
        flash(f"Failed to confirm booking: {e}", 'error')
        return redirect(url_for("bus_booking"))

# Train Booking API
@app.route('/api/book_train', methods=['POST'])
def api_book_train():
    if 'email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    booking_data = {
        'user_email': session['email'],
        'booking_type': 'train',
        'booking_id': str(uuid.uuid4()),
        'booking_date': datetime.now().isoformat(),
        'name': data.get('trainName'),
        'train_number': data.get('trainNumber'),
        'source': data.get('from'),
        'destination': data.get('to'),
        'travel_date': data.get('date'),
        'seats_display': data.get('seat'),
        'total_price': Decimal(str(data.get('price', 0))),
        'status': 'Confirmed'
    }

    try:
        bookings_table.put_item(Item=booking_data)
        
        send_sns_notification(
            subject="Train Booking Confirmed",
            message=f"Dear {booking_data['user_email']},\nYour train booking is confirmed.\nTrain: {booking_data['name']} ({booking_data['train_number']})\nSeats: {booking_data['seats_display']}\nTotal Price: ₹{booking_data['total_price']}"
        )
        
        return jsonify({'message': 'Train booked successfully!'}), 200
    except Exception as e:
        print(f"Error booking train: {e}")
        return jsonify({'error': str(e)}), 500

# Flight Booking
@app.route('/book_flight', methods=['POST'])
def book_flight():
    if 'email' not in session:
        return redirect(url_for('login'))
    
    booking_data = {
        'user_email': session['email'],
        'booking_type': 'flight',
        'booking_id': str(uuid.uuid4()),
        'booking_date': datetime.now().isoformat(),
        'source': request.form.get('from'),
        'destination': request.form.get('to'),
        'travel_date': request.form.get('date'),
        'seats_display': request.form.get('seat'),
        'total_price': Decimal(str(request.form.get('price', 0))),
        'status': 'Confirmed'
    }
    
    try:
        bookings_table.put_item(Item=booking_data)
        
        send_sns_notification(
            subject="Flight Booking Confirmed",
            message=f"Dear {booking_data['user_email']},\nYour flight booking is confirmed.\nRoute: {booking_data['source']} to {booking_data['destination']}\nDate: {booking_data['travel_date']}\nTotal Price: ₹{booking_data['total_price']}"
        )
        
        flash("Flight ticket booked successfully!", "success")
        return redirect(url_for('dashboard'))
    except Exception as e:
        print(f"Error booking flight: {e}")
        flash(f"Failed to book flight: {e}", "error")
        return redirect(url_for('flight_booking'))

# Hotel Booking API
@app.route('/api/book_hotel', methods=['POST'])
def api_book_hotel():
    if 'email' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    booking_data = {
        'user_email': session['email'],
        'booking_type': 'hotel',
        'booking_id': str(uuid.uuid4()),
        'booking_date': datetime.now().isoformat(),
        'name': data.get('hotelName'),
        'location': data.get('location'),
        'checkin_date': data.get('checkIn'),
        'checkout_date': data.get('checkOut'),
        'num_guests': int(data.get('guests', 1)),
        'room_type': data.get('roomType'),
        'total_price': Decimal(str(data.get('price', 0))),
        'status': 'Confirmed'
    }

    try:
        bookings_table.put_item(Item=booking_data)
        
        send_sns_notification(
            subject="Hotel Booking Confirmed",
            message=f"Dear {booking_data['user_email']},\nYour hotel booking is confirmed.\nHotel: {booking_data['name']}\nLocation: {booking_data['location']}\nCheck-in: {booking_data['checkin_date']}\nCheck-out: {booking_data['checkout_date']}\nTotal Price: ₹{booking_data['total_price']}"
        )
        
        return jsonify({"message": "Hotel booked and saved!"}), 200
    except Exception as e:
        print(f"Error booking hotel: {e}")
        return jsonify({"error": str(e)}), 500

# Cancel Booking
@app.route('/cancel_booking', methods=['POST'])
def cancel_booking():
    if 'email' not in session:
        return redirect(url_for('login'))

    booking_id = request.form.get('booking_id')
    user_email = session['email']
    booking_date = request.form.get('booking_date')

    if not booking_id or not booking_date:
        flash("Error: Booking ID or Booking Date is missing for cancellation.", 'error')
        return redirect(url_for('dashboard'))

    try:
        bookings_table.delete_item(
            Key={'user_email': user_email, 'booking_date': booking_date}
        )
        flash(f"Booking {booking_id} cancelled successfully!", 'success')
        
        send_sns_notification(
            subject="Booking Cancelled",
            message=f"Dear {user_email},\nYour booking {booking_id} has been cancelled successfully."
        )
        
    except Exception as e:
        print(f"Error cancelling booking: {e}")
        flash(f"Failed to cancel booking {booking_id}: {str(e)}", 'error')

    return redirect(url_for('dashboard'))

if _name_ == '_main_':
    app.run(debug=True, host='0.0.0.0', port=5000)
