# RoluATM Deployment Checklist

## 🔴 PHASE 1: IMMEDIATE DEPLOYMENT (Est: 30 minutes)

### Cloud API Deployment
- [ ] Deploy to Vercel
  ```bash
  cd cloud-api
  vercel --prod
  ```
- [ ] Set Vercel environment variables:
  - [ ] `NEON_DATABASE_URL=postgresql://username:password@host/database`
  - [ ] `WORLD_ID_APP_ID=app_263013ca6f702add37ad338fa43d4307`
  - [ ] `WORLD_ID_ACTION=withdraw-cash`
- [ ] Test endpoints:
  - [ ] `GET https://your-app.vercel.app/test`
  - [ ] `GET https://your-app.vercel.app/health`

### Kiosk Environment Setup
- [ ] Create kiosk backend environment:
  ```bash
  cp kiosk-pi/.env.example kiosk-pi/.env
  nano kiosk-pi/.env  # Edit with your values
  ```
- [ ] Create frontend environment:
  ```bash
  cp kiosk-pi/frontend/.env.example kiosk-pi/frontend/.env.local
  nano kiosk-pi/frontend/.env.local  # Set VITE_CLOUD_API_URL
  ```

### Quick Deployment Test
- [ ] Test cloud API connectivity
- [ ] Test hardware driver (if available)
- [ ] Test frontend build process

## 🟡 PHASE 2: PRODUCTION HARDENING (Est: 2 hours)

### Testing Infrastructure
- [ ] Create frontend unit tests
- [ ] Create integration tests
- [ ] Create E2E test suite
- [ ] Set up automated testing

### Security Enhancements
- [ ] Configure production CORS origins
- [ ] Set up SSL certificates
- [ ] Implement rate limiting
- [ ] Add request validation
- [ ] Set up audit logging

### Monitoring & Observability
- [ ] Set up Grafana dashboard
- [ ] Configure alerting
- [ ] Set up log aggregation
- [ ] Implement health check monitoring

## 🟢 PHASE 3: OPERATIONAL EXCELLENCE (Est: 4 hours)

### Documentation
- [ ] API documentation
- [ ] Hardware setup guide
- [ ] Troubleshooting guide
- [ ] Operator manual

### Advanced Features
- [ ] Remote management
- [ ] Automated updates
- [ ] Performance optimization
- [ ] Load testing

### Business Continuity
- [ ] Backup procedures
- [ ] Disaster recovery
- [ ] Maintenance schedules
- [ ] Support procedures

## 📊 COMPLETION CRITERIA

- [ ] All tests passing
- [ ] Monitoring operational
- [ ] Documentation complete
- [ ] Security review passed
- [ ] Performance benchmarks met
- [ ] Operator training complete 