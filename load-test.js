import http from 'k6/http';
import { check, sleep } from 'k6';

// Configure the load test phases and pass/fail criteria
export const options = {
  stages: [
    { duration: '10s', target: 50 }, // Ramp up to 50 concurrent virtual users
    { duration: '30s', target: 50 }, // Hold peak load for 30 seconds
    { duration: '10s', target: 0 },  // Gracefully scale down
  ],
  thresholds: {
    // We expect 95% of these bulk-insert requests to finish in under 200ms
    http_req_duration: ['p(95)<200'], 
    // We expect a 0% failure rate
    http_req_failed: ['rate==0'],     
  },
};

// Define the continuous behavior for each Virtual User
export default function () {
  // Use host.docker.internal if running k6 via Docker on Mac/Windows
  const url = 'http://host.docker.internal:8000/server-metrics/';
  
  // Generate a dynamic batch of 100 metrics matching the ServerMetricCreate schema
  const payload = [];
  for (let i = 0; i < 100; i++) {
    payload.push({
      user_id: `user-${Math.floor(Math.random() * 1000).toString().padStart(4, '0')}`,
      user_token: parseFloat((Math.random() * 100).toFixed(2))
    });
  }

  const params = {
    headers: { 'Content-Type': 'application/json' },
  };

  // POST to the FastAPI endpoint
  const res = http.post(url, JSON.stringify(payload), params);

  // Verify the response is a successful 201 Created
  check(res, {
    'is status 201': (r) => r.status === 201,
  });

  // Short pause to avoid overwhelming the local network stack
  sleep(0.1); 
}
