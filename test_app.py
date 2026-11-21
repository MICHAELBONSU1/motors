import os
import unittest
import json
import io
import time

TEST_DB_PATH = os.path.join(os.path.dirname(__file__), 'test_isolated_db.sqlite')
os.environ['DATABASE_PATH'] = TEST_DB_PATH

from app import app
from database import init_db, get_db

class BigLAutosTestCase(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        try:
            if os.path.exists(TEST_DB_PATH):
                os.remove(TEST_DB_PATH)
        except Exception:
            pass

    def setUp(self):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret-key'
        self.client = app.test_client()
        init_db()
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT id FROM cars WHERE make = 'Toyota' LIMIT 1")
        if not cursor.fetchone():
            cursor.execute('''
            INSERT INTO cars (seller_id, title, make, model, year, price, mileage, transmission, fuel_type, body_type, color, condition, status, description, features, image_url, images)
            VALUES (1, '2022 Toyota Land Cruiser Prado TX-L', 'Toyota', 'Land Cruiser Prado', 2022, 920000, 26000, 'Automatic', 'Diesel', 'SUV', 'Pearl White', 'Foreign Used', 'Available', 'Test car', '4x4', 'https://images.unsplash.com/photo-1594502184342-2e12f877aa73?auto=format&fit=crop&w=1200&q=80', '[]')
            ''')
            db.commit()
        db.close()

    def test_home_page(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'BIG-L AUTOS', response.data)
        self.assertIn(b'YOUR NEXT CAR', response.data)
        self.assertIn(b'AWAITS YOU', response.data)
        self.assertIn(b'WE SELL', response.data)
        self.assertIn(b'WE BUY', response.data)
        self.assertIn(b'WE SWAP', response.data)

    def test_cars_api_and_filters(self):
        response = self.client.get('/api/cars')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('cars', data)
        self.assertGreater(len(data['cars']), 0)
        first_car = data['cars'][0]
        self.assertIn('title', first_car)
        self.assertIn('price', first_car)
        self.assertIn('condition', first_car)

        # Test filter by make
        res_filter = self.client.get('/api/cars?make=Toyota')
        self.assertEqual(res_filter.status_code, 200)
        filtered = json.loads(res_filter.data)['cars']
        for car in filtered:
            self.assertEqual(car['make'], 'Toyota')

    def test_auth_registration_and_inquiry_flow(self):
        unique_email = f"buyer_{int(time.time()*1000)}@example.com"
        reg_payload = {
            'name': 'James Miller',
            'email': unique_email,
            'phone': '0549255121',
            'password': 'millerpass123'
        }
        reg_res = self.client.post('/api/auth/register', json=reg_payload)
        self.assertEqual(reg_res.status_code, 200)
        reg_data = json.loads(reg_res.data)
        self.assertTrue(reg_data['success'])

        # Attempt registering same email again -> must return 409 and prompt to login
        dup_reg = self.client.post('/api/auth/register', json=reg_payload)
        self.assertEqual(dup_reg.status_code, 409)
        dup_data = json.loads(dup_reg.data)
        self.assertTrue(dup_data.get('already_exists'))
        self.assertIn('already have an account', dup_data.get('error', '').lower())

        cars_res = self.client.get('/api/cars')
        car_id = json.loads(cars_res.data)['cars'][0]['id']

        inquiry_res = self.client.post('/api/inquiries/start', json={'car_id': car_id})
        self.assertEqual(inquiry_res.status_code, 200)
        inquiry_data = json.loads(inquiry_res.data)
        self.assertTrue(inquiry_data['success'])
        chat_id = inquiry_data['chat_id']

        msg_res = self.client.get(f'/api/chats/{chat_id}/messages')
        self.assertEqual(msg_res.status_code, 200)
        msg_data = json.loads(msg_res.data)
        self.assertGreater(len(msg_data['messages']), 0)
        self.assertEqual(msg_data['messages'][0]['sender_role'], 'support')

        send_res = self.client.post(f'/api/chats/{chat_id}/messages', json={'message': 'Can you take GH₵ 1,100,000 cash?'})
        self.assertEqual(send_res.status_code, 200)

        msg_res2 = self.client.get(f'/api/chats/{chat_id}/messages')
        messages2 = json.loads(msg_res2.data)['messages']
        self.assertEqual(len(messages2), 2)
        self.assertEqual(messages2[1]['message'], 'Can you take GH₵ 1,100,000 cash?')

        # Authenticate properly as admin using real credentials
        admin_login_res = self.client.post('/api/auth/login', json={'email': 'admin@biglautos.com', 'password': 'admin123'})
        self.assertEqual(admin_login_res.status_code, 200)

        admin_reply = self.client.post(f'/api/chats/{chat_id}/messages', json={'message': 'We can do GH₵ 1,140,000 for cash buyers at Somanya-Roundabout!'})
        self.assertEqual(admin_reply.status_code, 200)

        msg_res3 = self.client.get(f'/api/chats/{chat_id}/messages')
        messages3 = json.loads(msg_res3.data)['messages']
        self.assertEqual(len(messages3), 3)
        self.assertEqual(messages3[2]['sender_role'], 'admin')
        self.assertEqual(messages3[2]['message'], 'We can do GH₵ 1,140,000 for cash buyers at Somanya-Roundabout!')

    def test_login_and_register_pages(self):
        login_res = self.client.get('/login')
        self.assertEqual(login_res.status_code, 200)
        self.assertIn(b'BIG-L AUTOS', login_res.data)
        self.assertIn(b'advanced-auth-container', login_res.data)
        self.assertIn(b'Sign In', login_res.data)

        reg_res = self.client.get('/register')
        self.assertEqual(reg_res.status_code, 200)
        self.assertIn(b'BIG-L AUTOS', reg_res.data)
        self.assertIn(b'advanced-auth-container', reg_res.data)
        self.assertIn(b'Create Your Account', reg_res.data)

    def test_admin_upload_car_and_manage(self):
        admin_login = self.client.post('/api/auth/login', json={'email': 'admin@biglautos.com', 'password': 'admin123'})
        self.assertEqual(admin_login.status_code, 200)

        car_data = {
            'title': f'2025 Porsche 911 Carrera GTS {int(time.time())}',
            'make': 'Porsche',
            'model': '911 Carrera GTS',
            'year': '2025',
            'price': '145000',
            'mileage': '1200',
            'transmission': 'Automatic',
            'fuel_type': 'Petrol',
            'body_type': 'Coupe',
            'color': 'Guards Red',
            'condition': 'Brand New',
            'status': 'Available',
            'description': 'Twin-turbocharged coupe in pristine showroom condition.',
            'features': 'Sport Chrono Package, Ceramic Brakes, BOSE Audio',
            'image_file': (io.BytesIO(b"fake image data"), "porsche_911.jpg")
        }
        res = self.client.post('/api/cars', data=car_data, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(data['success'])
        car_id = data['car_id']

        car_res = self.client.get(f'/api/cars/{car_id}')
        self.assertEqual(car_res.status_code, 200)
        car = json.loads(car_res.data)['car']
        self.assertEqual(car['make'], 'Porsche')
        self.assertEqual(car['price'], 145000)

        update_res = self.client.put(f'/api/cars/{car_id}', json={'status': 'Reserved'})
        self.assertEqual(update_res.status_code, 200)

        car_res2 = self.client.get(f'/api/cars/{car_id}')
        self.assertEqual(json.loads(car_res2.data)['car']['status'], 'Reserved')

    def test_security_hardening(self):
        # 1. Backdoor demo-login route must be completely removed (404)
        demo_res = self.client.post('/api/auth/demo-login', json={'role': 'admin'})
        self.assertEqual(demo_res.status_code, 404)

        # 2. Security response headers must be present
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get('X-Frame-Options'), 'SAMEORIGIN')
        self.assertEqual(res.headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(res.headers.get('X-XSS-Protection'), '1; mode=block')
        self.assertIn('Content-Security-Policy', res.headers)

        # 3. Weak password rejection (< 6 chars)
        weak_reg = self.client.post('/api/auth/register', json={
            'name': 'Test Weak',
            'email': f'weak_{int(time.time())}@example.com',
            'phone': '0549255121',
            'password': '123'
        })
        self.assertEqual(weak_reg.status_code, 400)
        self.assertIn('at least 6 characters', json.loads(weak_reg.data)['error'])

        # 4. Invalid email rejection
        bad_email = self.client.post('/api/auth/register', json={
            'name': 'Test Bad',
            'email': 'not-an-email',
            'phone': '0549255121',
            'password': 'validpassword123'
        })
        self.assertEqual(bad_email.status_code, 400)

        # 5. Rate limiting on repeated failed logins (brute force block)
        target_email = f"brute_victim_{int(time.time())}@example.com"
        for _ in range(5):
            bad_login = self.client.post('/api/auth/login', json={
                'email': target_email,
                'password': 'wrongpassword'
            })
            self.assertEqual(bad_login.status_code, 401)

        # 6th attempt should be blocked with 429 Too Many Requests
        blocked_login = self.client.post('/api/auth/login', json={
            'email': target_email,
            'password': 'wrongpassword'
        })
        self.assertEqual(blocked_login.status_code, 429)
        self.assertIn('locked', json.loads(blocked_login.data)['error'])

    def test_user_car_direct_seller_inquiry(self):
        # 1. Register a seller user
        seller_email = f"seller_{int(time.time()*1000)}@example.com"
        s_res = self.client.post('/api/auth/register', json={
            'name': 'Kwame Seller',
            'email': seller_email,
            'phone': '0244112233',
            'password': 'sellerpassword123'
        })
        self.assertEqual(s_res.status_code, 200)
        seller_id = json.loads(s_res.data)['user']['id']

        # 2. Login as admin and approve seller profile
        admin_login = self.client.post('/api/auth/login', json={'email': 'admin@biglautos.com', 'password': 'admin123'})
        self.assertEqual(admin_login.status_code, 200)
        appr_res = self.client.post(f'/api/admin/sellers/{seller_id}/access', json={'action': 'approve'})
        self.assertEqual(appr_res.status_code, 200)

        # 3. Login as seller and post a car
        self.client.post('/api/auth/login', json={'email': seller_email, 'password': 'sellerpassword123'})
        post_res = self.client.post('/api/cars', json={
            'title': '2021 Honda Civic Type R',
            'make': 'Honda',
            'model': 'Civic',
            'year': 2021,
            'price': 280000,
            'mileage': 22000,
            'transmission': 'Manual',
            'fuel_type': 'Petrol',
            'body_type': 'Hatchback',
            'color': 'Championship White',
            'condition': 'Foreign Used',
            'status': 'Available',
            'description': 'Pristine hot hatch, all stock.',
            'features': 'Brembo Brakes, Recaro Seats'
        })
        self.assertEqual(post_res.status_code, 200)
        seller_car_id = json.loads(post_res.data)['car_id']

        # 4. Verify car listing has is_user_seller = True
        car_res = self.client.get(f'/api/cars/{seller_car_id}')
        self.assertEqual(car_res.status_code, 200)
        car_info = json.loads(car_res.data)['car']
        self.assertTrue(car_info['is_user_seller'])
        self.assertEqual(car_info['seller_name'], 'Kwame Seller')

        # 5. Seller attempts to text themselves -> blocked with friendly error
        self_inquiry = self.client.post('/api/inquiries/start', json={'car_id': seller_car_id})
        self.assertEqual(self_inquiry.status_code, 400)
        self.assertTrue(json.loads(self_inquiry.data).get('is_owner'))

        # 6. Register a buyer user
        buyer_email = f"buyer_{int(time.time()*1000)}@example.com"
        b_res = self.client.post('/api/auth/register', json={
            'name': 'Ama Buyer',
            'email': buyer_email,
            'phone': '0200998877',
            'password': 'buyerpassword123'
        })
        self.assertEqual(b_res.status_code, 200)

        # 7. Buyer clicks to text about the user's posted car -> texts Kwame Seller directly!
        buyer_inquiry = self.client.post('/api/inquiries/start', json={'car_id': seller_car_id})
        self.assertEqual(buyer_inquiry.status_code, 200)
        inquiry_data = json.loads(buyer_inquiry.data)
        chat_id = inquiry_data['chat_id']

        # Buyer checks messages: initial message is addressed to the seller Kwame
        b_msgs = self.client.get(f'/api/chats/{chat_id}/messages')
        self.assertEqual(b_msgs.status_code, 200)
        b_chat_info = json.loads(b_msgs.data)['chat']
        self.assertEqual(b_chat_info['other_party_role'], 'Seller')
        self.assertEqual(b_chat_info['other_party_name'], 'Kwame Seller')
        self.assertEqual(b_chat_info['chat_type'], 'buying')

        # 8. Seller logs in, checks chats, sees "Buyer Inquiry" from Ama Buyer!
        self.client.post('/api/auth/login', json={'email': seller_email, 'password': 'sellerpassword123'})
        s_chats_res = self.client.get('/api/chats')
        self.assertEqual(s_chats_res.status_code, 200)
        s_chats = json.loads(s_chats_res.data)['chats']
        self.assertEqual(len(s_chats), 1)
        self.assertEqual(s_chats[0]['chat_type'], 'selling')
        self.assertEqual(s_chats[0]['other_party_role'], 'Buyer')
        self.assertEqual(s_chats[0]['other_party_name'], 'Ama Buyer')

        # 9. Seller replies to Ama directly
        s_reply = self.client.post(f'/api/chats/{chat_id}/messages', json={'message': 'Hello Ama, yes it is available! When would you like to inspect it?'})
        self.assertEqual(s_reply.status_code, 200)

        # 10. Buyer logs back in and reads Kwame's reply
        self.client.post('/api/auth/login', json={'email': buyer_email, 'password': 'buyerpassword123'})
        b_final = self.client.get(f'/api/chats/{chat_id}/messages')
        final_msgs = json.loads(b_final.data)['messages']
        self.assertEqual(len(final_msgs), 2)
        self.assertEqual(final_msgs[1]['sender_name'], 'Kwame Seller')
        self.assertIn('available', final_msgs[1]['message'])

    def test_admin_account_management_and_deletion(self):
        # 1. Register a test customer
        cust_email = f"delete_me_{int(time.time() * 1000)}@example.com"
        reg_res = self.client.post('/api/auth/register', json={
            'name': 'Test ToDelete',
            'email': cust_email,
            'phone': '0240009999',
            'password': 'password123'
        })
        self.assertEqual(reg_res.status_code, 200)
        cust_id = json.loads(reg_res.data)['user']['id']

        # 2. Customer creates a chat inquiry
        cars_res = self.client.get('/api/cars')
        car_id = json.loads(cars_res.data)['cars'][0]['id']
        inq_res = self.client.post('/api/inquiries/start', json={'car_id': car_id})
        self.assertEqual(inq_res.status_code, 200)

        # 3. Customer attempts to delete an account (must be 403 forbidden)
        unauth_del = self.client.delete(f'/api/admin/users/{cust_id}')
        self.assertEqual(unauth_del.status_code, 403)

        # 4. Admin logs in
        admin_login = self.client.post('/api/auth/login', json={'email': 'admin@biglautos.com', 'password': 'admin123'})
        self.assertEqual(admin_login.status_code, 200)

        # 5. Admin lists accounts via /api/admin/users
        users_res = self.client.get('/api/admin/users')
        self.assertEqual(users_res.status_code, 200)
        users_data = json.loads(users_res.data)
        self.assertIn('users', users_data)
        user_ids = [u['id'] for u in users_data['users']]
        self.assertIn(cust_id, user_ids)
        self.assertIn(1, user_ids)

        # 6. Admin searches for the user
        search_res = self.client.get('/api/admin/users?q=ToDelete')
        self.assertEqual(search_res.status_code, 200)
        search_users = json.loads(search_res.data)['users']
        self.assertEqual(len(search_users), 1)
        self.assertEqual(search_users[0]['id'], cust_id)

        # 7. Admin attempts to delete primary admin (id 1) - must be protected (403)
        del_admin_res = self.client.delete('/api/admin/users/1')
        self.assertEqual(del_admin_res.status_code, 403)
        self.assertIn('protected', json.loads(del_admin_res.data)['error'].lower())

        # 8. Admin deletes the customer account
        del_res = self.client.delete(f'/api/admin/users/{cust_id}')
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(json.loads(del_res.data)['success'])

        # 9. Verify user no longer exists in database
        users_after = json.loads(self.client.get('/api/admin/users').data)['users']
        self.assertNotIn(cust_id, [u['id'] for u in users_after])

        # 10. Verify chats were cascaded
        chats_after = json.loads(self.client.get('/api/chats').data)['chats']
        self.assertNotIn(cust_id, [c['customer_id'] for c in chats_after])

    def test_social_login(self):
        social_email = f"social_{int(time.time()*1000)}@gmail.com"
        # 1. First-time social sign-in (auto-creates account)
        res = self.client.post('/api/auth/social-login', json={
            'provider': 'google',
            'email': social_email,
            'name': 'Kofi Google'
        })
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(data['success'])
        self.assertTrue(data['is_new_user'])
        self.assertEqual(data['user']['email'], social_email)
        self.assertEqual(data['user']['name'], 'Kofi Google')

        # 2. Returning social sign-in (logs directly in without filling forms)
        res2 = self.client.post('/api/auth/social-login', json={
            'provider': 'google',
            'email': social_email
        })
        self.assertEqual(res2.status_code, 200)
        data2 = json.loads(res2.data)
        self.assertTrue(data2['success'])
        self.assertFalse(data2['is_new_user'])
        self.assertEqual(data2['user']['email'], social_email)

        # 3. Social login creates/logs in as regular customer (buyer/seller)
        cust_social = self.client.post('/api/auth/social-login', json={
            'provider': 'google',
            'email': 'bonsum114@gmail.com',
            'name': 'Michael Bonsu'
        })
        self.assertEqual(cust_social.status_code, 200)
        cust_data = json.loads(cust_social.data)
        self.assertTrue(cust_data['success'])
        self.assertEqual(cust_data['user']['role'], 'customer')
        self.assertEqual(cust_data['redirect'], '/customer')

        # 4. Larry's admin email cannot be hijacked via social login
        admin_blocked = self.client.post('/api/auth/social-login', json={
            'provider': 'google',
            'email': 'admin@biglautos.com',
            'name': 'Hacker'
        })
        self.assertEqual(admin_blocked.status_code, 403)

    def test_user_profile_and_password_update(self):
        test_email = f"user_{int(time.time()*1000)}@test.com"
        reg = self.client.post('/api/auth/register', json={
            'name': 'Original Name',
            'email': test_email,
            'phone': '0240001111',
            'password': 'oldpassword123'
        })
        self.assertEqual(reg.status_code, 200)

        # 1. Update Profile (Name & Phone)
        up_res = self.client.post('/api/user/profile', json={
            'name': 'Updated Name',
            'phone': '0549998888',
            'email': test_email
        })
        self.assertEqual(up_res.status_code, 200)
        up_data = json.loads(up_res.data)
        self.assertTrue(up_data['success'])
        self.assertEqual(up_data['user']['name'], 'Updated Name')
        self.assertEqual(up_data['user']['phone'], '0549998888')

        # 2. Attempt password update with wrong current password
        bad_pw = self.client.post('/api/user/change-password', json={
            'current_password': 'wrongpassword',
            'new_password': 'newpassword123'
        })
        self.assertEqual(bad_pw.status_code, 400)
        self.assertIn('incorrect', json.loads(bad_pw.data)['error'].lower())

        # 3. Successful password update
        good_pw = self.client.post('/api/user/change-password', json={
            'current_password': 'oldpassword123',
            'new_password': 'newpassword123'
        })
        self.assertEqual(good_pw.status_code, 200)
        self.assertTrue(json.loads(good_pw.data)['success'])

        # 4. Verify login with new password works
        self.client.post('/api/auth/logout')
        login_res = self.client.post('/api/auth/login', json={
            'email': test_email,
            'password': 'newpassword123'
        })
        self.assertEqual(login_res.status_code, 200)

    def test_oauth_popup_routes(self):
        # Verify Google OAuth popup route returns 200 and branded HTML
        google_res = self.client.get('/auth/google')
        self.assertEqual(google_res.status_code, 200)
        self.assertIn(b'Continue with Google', google_res.data)

        # Verify Apple OAuth popup route returns 200 and branded HTML
        apple_res = self.client.get('/auth/apple')
        self.assertEqual(apple_res.status_code, 200)
        self.assertIn(b'Sign in with Apple', apple_res.data)
        self.assertIn(b'Apple ID', apple_res.data)
        self.assertIn(b'Continue with Apple', apple_res.data)

if __name__ == '__main__':
    unittest.main()
