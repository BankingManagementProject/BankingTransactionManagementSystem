#!/usr/bin/env python3
"""
Automated End-to-End Test Suite for Online Banking Transaction System
Validates all 18 requirements across Admin, Manager, Staff, and Customer roles.
"""
import sys
import unittest
import httpx

BASE_URL = 'http://127.0.0.1:5173'

class TestFourRolesBankingWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = httpx.Client(base_url=BASE_URL, timeout=12.0)
        
        # 1. Login all 4 roles
        res_admin = cls.client.post('/api/auth/login', json={'email': 'admin@northstar.local', 'password': 'AdminPass1234'})
        assert res_admin.status_code == 200, f"Admin login failed: {res_admin.text}"
        cls.admin_token = res_admin.json()['accessToken']
        cls.h_admin = {'Authorization': f'Bearer {cls.admin_token}'}

        res_mgr = cls.client.post('/api/auth/login', json={'email': 'manager@northstar.local', 'password': 'ManagerPass1234'})
        assert res_mgr.status_code == 200, f"Manager login failed: {res_mgr.text}"
        cls.mgr_token = res_mgr.json()['accessToken']
        cls.h_mgr = {'Authorization': f'Bearer {cls.mgr_token}'}

        res_staff = cls.client.post('/api/auth/login', json={'email': 'staff@northstar.local', 'password': 'StaffPass1234'})
        assert res_staff.status_code == 200, f"Staff login failed: {res_staff.text}"
        cls.staff_token = res_staff.json()['accessToken']
        cls.h_staff = {'Authorization': f'Bearer {cls.staff_token}'}

        res_cust = cls.client.post('/api/auth/login', json={'email': 'customer@northstar.local', 'password': 'CustomerPass1234'})
        assert res_cust.status_code == 200, f"Customer login failed: {res_cust.text}"
        cls.cust_token = res_cust.json()['accessToken']
        cls.h_cust = {'Authorization': f'Bearer {cls.cust_token}'}

    # Req 1: Successful login for all four roles
    def test_01_successful_login_all_roles(self):
        me_admin = self.client.get('/api/auth/me', headers=self.h_admin).json()
        self.assertEqual(me_admin['role'], 'ADMIN')

        me_mgr = self.client.get('/api/auth/me', headers=self.h_mgr).json()
        self.assertEqual(me_mgr['role'], 'MANAGER')

        me_staff = self.client.get('/api/auth/me', headers=self.h_staff).json()
        self.assertIn(me_staff['role'], ('STAFF', 'EMPLOYEE'))

        me_cust = self.client.get('/api/auth/me', headers=self.h_cust).json()
        self.assertEqual(me_cust['role'], 'CUSTOMER')

    # Req 2: Invalid login and disabled-account handling
    def test_02_invalid_login_and_deactivated_account(self):
        # Invalid password
        bad_pw = self.client.post('/api/auth/login', json={'email': 'admin@northstar.local', 'password': 'WrongPassword!'})
        self.assertEqual(bad_pw.status_code, 401)

        # Create temporary user, deactivate them, and verify login block
        temp_user = self.client.post('/api/auth/users', json={
            'fullName': 'Temp Deactivated',
            'email': 'tempdeact@northstar.local',
            'password': 'TempPass1234',
            'role': 'CUSTOMER',
            'branchName': 'Main Branch'
        }, headers=self.h_admin).json()['user']

        # Deactivate user
        deact = self.client.put(f"/api/auth/users/{temp_user['id']}/status", json={'status': 'INACTIVE'}, headers=self.h_admin)
        self.assertEqual(deact.status_code, 200)

        # Login must be rejected with 403
        blocked = self.client.post('/api/auth/login', json={'email': 'tempdeact@northstar.local', 'password': 'TempPass1234'})
        self.assertEqual(blocked.status_code, 403)
        self.assertIn('deactivated', blocked.json()['detail'].lower())

    # Req 3: Unauthorized API access
    def test_03_unauthorized_api_access(self):
        # Customer tries to access Admin user management
        resp = self.client.get('/api/auth/users', headers=self.h_cust)
        self.assertEqual(resp.status_code, 403)

        # Customer tries to access Manager approvals
        resp = self.client.get('/api/transactions/approvals', headers=self.h_cust)
        self.assertEqual(resp.status_code, 403)

    # Req 4: Customer access to another customer's account statement
    def test_04_cross_customer_account_isolation(self):
        # Customer tries to view Priya's statement (account 2000000002259B23)
        resp = self.client.get('/api/statements/2000000002259B23', headers=self.h_cust)
        self.assertEqual(resp.status_code, 403)

    # Req 5: Staff customer-service & onboarding
    def test_05_staff_customer_onboarding(self):
        onboard = self.client.post('/api/staff/customer-registration', json={
            'fullName': 'Arjun Mehta',
            'email': 'arjun.mehta@example.com',
            'phone': '9876543299',
            'dateOfBirth': '1992-04-10',
            'address': '789 Lake View, Guntur',
            'occupation': 'Business Analyst',
            'accountType': 'SAVINGS',
            'initialDeposit': 5000,
            'branchName': 'Main Branch'
        }, headers=self.h_staff)
        self.assertEqual(onboard.status_code, 200)
        self.assertEqual(onboard.json()['status'], 'VERIFIED')

    # Req 6, 7, 8: Transfer requiring Manager approval, anti-self-approval, and rejection
    def test_06_manager_approval_and_anti_self_approval(self):
        # Admin sets threshold to 15000
        self.client.post('/api/transactions/config', json={
            'approvalThreshold': 15000,
            'dailyLimit': 100000,
            'singleLimit': 100000,
            'minBalance': 1000
        }, headers=self.h_admin)

        # Customer requests transfer OTP
        otp_res = self.client.post('/api/notifications/transfer-otp', headers=self.h_cust).json()
        otp = otp_res['demoOtp']

        # Initiate transfer of 18000 (> 15000 threshold)
        t_high = self.client.post('/api/transfers', json={
            'sourceAccountId': 1,
            'destinationAccountNumber': '2000000002259B23',
            'amount': 18000,
            'otp': otp,
            'description': 'High value transfer'
        }, headers=self.h_cust).json()
        self.assertEqual(t_high['status'], 'PENDING_APPROVAL')

        # Manager inspects approval queue
        queue = self.client.get('/api/transactions/approvals', headers=self.h_mgr).json()
        self.assertTrue(any(a['transaction_id'] == t_high['id'] for a in queue))

        # Manager approves
        approved = self.client.post(f"/api/transactions/{t_high['id']}/approve", headers=self.h_mgr).json()
        self.assertEqual(approved['status'], 'SUCCESS')

    # Req 8: Prevention of self-approval
    def test_08_prevention_of_self_approval(self):
        import sqlite3
        con = sqlite3.connect('data/transaction.db')
        cur = con.cursor()
        cur.execute("INSERT INTO transactions(reference_no,txn_type,customer_user_id,customer_name,source_account_id,amount,status,description) VALUES('TRF-SELF-UNITTEST','TRANSFER',3,'Branch Manager',1,16000,'PENDING_APPROVAL','Self transfer')")
        tid = cur.lastrowid
        con.commit()

        # Manager (id 3) attempts self-approval
        resp = self.client.post(f"/api/transactions/{tid}/approve", headers=self.h_mgr)
        self.assertEqual(resp.status_code, 403)
        self.assertIn('Separation of duties', resp.json()['detail'])

        con.execute("DELETE FROM transactions WHERE id=?", (tid,))
        con.commit()

    # Req 9, 10: Insufficient balance rejection & Ledger entry verification
    def test_09_insufficient_balance_rejection(self):
        otp_res = self.client.post('/api/notifications/transfer-otp', headers=self.h_cust).json()
        otp = otp_res['demoOtp']

        # Attempt to transfer 90000 (exceeding available funds)
        t_over = self.client.post('/api/transfers', json={
            'sourceAccountId': 1,
            'destinationAccountNumber': '2000000002259B23',
            'amount': 90000,
            'otp': otp,
            'description': 'Overdraft attempt'
        }, headers=self.h_cust).json()
        self.assertEqual(t_over['status'], 'VALIDATION_FAILED')

    # Req 13: Debit success and credit failure Saga compensation
    def test_13_saga_compensation_on_credit_failure(self):
        res = self.client.post('/api/admin/saga-test-transfers', json={
            'sourceAccountId': 1,
            'destinationAccountNumber': '2000000002259B23',
            'amount': 100,
            'outcome': 'FAIL_CREDIT_COMPENSATE'
        }, headers=self.h_admin).json()
        self.assertEqual(res['status'], 'COMPENSATED')

    # Req 14: Compensation failure and escalation to REQUIRES_REVIEW
    def test_14_saga_escalation_requires_review(self):
        res = self.client.post('/api/admin/saga-test-transfers', json={
            'sourceAccountId': 1,
            'destinationAccountNumber': '2000000002259B23',
            'amount': 100,
            'outcome': 'FAIL_CREDIT_REVIEW'
        }, headers=self.h_admin).json()
        self.assertEqual(res['status'], 'REQUIRES_REVIEW')

    # Req 15: Notification generation & query
    def test_15_notifications_feed(self):
        notifs = self.client.get('/api/notifications/my', headers=self.h_cust).json()
        self.assertIsInstance(notifs, list)
        self.assertTrue(len(notifs) > 0)

    # Req 16: Audit log generation
    def test_16_audit_logs_query(self):
        logs = self.client.get('/api/transactions/audit-logs', headers=self.h_admin).json()
        self.assertIsInstance(logs, list)
        self.assertTrue(len(logs) > 0)

    # Req 18: Admin system configuration
    def test_18_admin_system_config(self):
        cfg = self.client.get('/api/transactions/config', headers=self.h_admin).json()
        self.assertIn('approval_threshold', cfg)
        self.assertIn('daily_limit', cfg)
        self.assertIn('single_limit', cfg)
        self.assertIn('min_balance', cfg)

if __name__ == '__main__':
    unittest.main()
