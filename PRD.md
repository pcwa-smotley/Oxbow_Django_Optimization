# Product Requirements Document (PRD)
## ABAY Reservoir Optimization System

**Version:** 1.0  
**Date:** September 2025
**Status:** In Development  
**Owner:** PCWA Energy Marketing Group

---

## 1. Executive Summary

The ABAY Reservoir Optimization System is a web-based application that optimizes water reservoir operations at the 
Afterbay (ABAY) facility. It uses linear programming to maximize operational efficiency while meeting recreational, 
environmental, and power generation requirements.

## 2. Problem Statement

### Current Challenges
- Manual reservoir management leads should incorporate complex rules
- Difficulty balancing competing demands (power generation, recreation, flood control)
- Alerting system is not fully set up and needs enhancement for timely operator notifications
- Need to integrate changes from user input on input page into optimization runs. 

### Opportunity
Automated optimization can improve:
- Power generation revenue by 10-15%
- Recreational flow reliability by 95%
- Operational efficiency by reducing manual interventions by 70%

## 3. Goals & Objectives

### Primary Goals
1. **Optimize Water Management**: Maximize efficient use of water resources
2. **Automate Operations**: Reduce manual decision-making from 8 hours/day to 1 hour/day
3. **Ensure Compliance**: Meet 100% of recreational flow requirements
4. **Maximize Revenue**: Optimize power generation during high-price periods
5. **Enhance Alerting**: Provide timely notifications for critical events

### Success Metrics
- Zero unplanned spills during normal operations
- 100% achievement of summer rafting flow targets
- 15% increase in power generation revenue
- 90% reduction in manual setpoint adjustments
- 100% compliance with minimum elevation requirements

## 4. User Personas

### Primary Users
1. **Reservoir Operators** (4-6 users)
   - Need: Real-time optimization guidance
   - Pain point: Manual calculations taking 2+ hours daily
   - Goal: Reliable setpoint recommendations

2. **System Engineers** (2-3 users)
   - Need: Performance monitoring and diagnostics
   - Pain point: Troubleshooting optimization failures
   - Goal: System reliability and accuracy

3. **Management** (1-2 users)
   - Need: Revenue and compliance reporting
   - Pain point: Lack of predictive analytics
   - Goal: Maximized revenue with risk mitigation

## 5. Functional Requirements

### 5.1 Core Optimization Engine
- **Linear Programming Solver**
  - Must solve 168-hour forecast horizon in <2 minutes
  - Support both forecast and historical simulation modes
  - Handle physical constraints (head loss, ramp rates)
  - Account for forecast uncertainty with R_bias correction

### 5.2 Data Integration
- **PI System Integration**
  - Real-time data ingestion every 5 minutes
  - Historical data access for bias calculation
  - 99.9% uptime requirement

- **Forecast Integration**
  - Upstream API for R4/R30 flow forecasts
  - MFRA generation forecasts (daily updates)
  - YES Energy price data (optional)

### 5.3 User Interface
- **Dashboard**
  - Real-time system status
  - 5-day optimization forecast
  - Interactive charts for elevation and generation
  - Mobile-responsive design

- **Alert Management**
  - Configurable thresholds by category
  - Multi-channel notifications (email, SMS, browser)
  - Rafting schedule alerts with ramp timing

### 5.4 Optimization Features
- **Constraints**
  - Minimum elevation: 1168.0 ft
  - OXPH capacity: 0.8 - 5.8 MW
  - Ramp rate: 0.042 MW/min
  - Head loss limitations above 4.5 MW
  - No summer spilling requirement

- **Objectives** (Prioritized)
  1. Avoid summer spills (Priority 1)
  2. Avoid general spillage (Priority 2)
  3. Meet summer rafting requirements (Priority 2)
  4. Smooth OXPH operations (Priority 3)
  5. Target midpoint elevation (Priority 4)

## 6. Technical Requirements

### 6.1 Architecture
- **Backend**: Django 4.2+ REST API
- **Frontend**: Vanilla JavaScript with real-time updates
- **Database**: SQLite with WAL mode (8 users max)
- **Optimization**: Python with PuLP/CBC solver
- **Real-time**: WebSockets for alerts

### 6.2 Performance
- Page load time: <2 seconds
- Optimization run time: <2 minutes
- API response time: <500ms
- Concurrent users: 8
- Data retention: 2 years

### 6.3 Security
- Django authentication
- HTTPS required
- Role-based permissions
- Audit logging for all changes
- Session timeout: 7 days with "Remember Me"

### 6.4 Integration Requirements
- PI Web API for real-time data
- Upstream.tech API for forecasts
- Twilio for SMS/voice alerts
- YES Energy API for prices (optional)

## 7. Non-Functional Requirements

### 7.1 Reliability
- 99.5% uptime during business hours
- Graceful degradation to simulation mode
- Automatic fallback for failed optimizations
- Data backup every 24 hours

### 7.2 Usability
- Single-page application
- No training required for basic use
- Clear error messages with actionable suggestions
- Accessible UI (WCAG 2.1 AA compliance)

### 7.3 Scalability
- Handle 7-day forecast horizon
- Process 1 year of historical data
- Support hourly optimization runs
- Accommodate seasonal rule changes

## 8. Feature Prioritization

### Phase 1 (MVP) - Completed
- [x] Basic optimization engine
- [x] PI System integration
- [x] Web dashboard
- [x] Forecast integration
- [x] Alert system initial version. 

### Phase 2 (Current)
- [ ] Enhanced diagnostics for failures
- [ ] Ensure correct function of linear_optimizer
- [ ] Revenue optimization with prices
- [ ] Advanced rafting schedule management
- [ ] Historical performance analytics

### Phase 3 (Future)
- [ ] Machine learning for forecast improvement
- [ ] Multi-reservoir optimization
- [ ] Mobile app
- [ ] Advanced reporting suite

## 9. Constraints & Assumptions

### Technical Constraints
- Must work within existing PI System
- Limited to 8 concurrent users
- Network dependency for VPN access
- Python 3.12+ requirement

### Business Constraints
- Zero tolerance for summer spills
- Must maintain existing Excel workflows during transition
- Operators must retain manual override capability

### Assumptions
- River flow forecasts are available via API
- Historical data for bias calculation is reliable
- Network connectivity is stable
- Users have modern browsers

## 10. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|---------|-------------|------------|
| Optimization infeasibility | High | Medium | Enhanced diagnostics, fallback modes |
| Forecast API failure | High | Low | Local persistence, manual entry |
| Network outages | Medium | Medium | Local simulation mode |
| User adoption | Medium | Low | Training, intuitive UI |

## 11. Success Criteria

### Short-term (3 months)
- Zero unplanned summer spills
- 90% of optimizations complete successfully
- All operators using system daily

### Long-term (1 year)
- 15% revenue increase documented
- 95% rafting requirement achievement
- Full retirement of manual Excel calculations

## 12. Appendices

### A. Glossary
- **ABAY**: Afterbay reservoir
- **OXPH**: Oxbow Powerhouse
- **MFRA**: Middle Fork and Ralston combined generation
- **CFS**: Cubic Feet per Second
- **AF**: Acre-Feet
- **MW**: Megawatts

### B. References
- Linear Programming Optimization Theory
- PCWA Operations Manual
- California Water Code Requirements
- FERC License Requirements

---

**Document Control**
- Created: December 2024
- Last Updated: December 2024
- Next Review: March 2025
- Distribution: Development Team, Operations, Management