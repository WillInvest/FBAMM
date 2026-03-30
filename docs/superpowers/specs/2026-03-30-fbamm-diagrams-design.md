# FBAMM Demo Diagrams — Design Spec

## Overview

Two static HTML/CSS diagrams demonstrating the FBAMM (Frequent Batch Auction AMM) mechanism. Target audience is DeFi-aware but not deeply technical — visual explanations over formulas.

## Deliverables

Two standalone HTML files with inline CSS/SVG, suitable for presentation or export as images.

## Diagram 1: FBAMM Mechanism Overview

**Purpose:** Show how FBAMM extends the traditional AMM state model from 2 to 4 variables, and how the interaction flow changes.

**Layout:**

- **Left side — Traditional AMM:** A box containing two state variables (X, Y reserves). A single arrow from "Swap" updates X and Y directly.
- **Right side — FBAMM:** A larger box containing:
  - An inner box for LP reserves (X, Y)
  - Two accumulator buckets above the LP: Qb (Buy Quantity) and Qs (Sell Quantity)
  - A dashed barrier between the accumulators and the LP reserves, labeled "Clearing required"
- **Actors:**
  - "Buyer" arrow points into Qb (not into LP)
  - "Seller" arrow points into Qs (not into LP)
- **Clearing arrow:** Crosses the dashed barrier from Qb/Qs down to LP reserves, labeled "Once per block — nets Qb vs Qs, remainder updates X, Y"
- **Bottom label:** "Unified price for all participants"

**Visual style:**
- Blue for buy side (Qb, buyer arrows)
- Orange/red for sell side (Qs, seller arrows)
- Green for LP reserves
- Clean boxes, black arrows, white background
- DeFi-presentation quality — polished but not flashy

## Diagram 2: Clearing Process Flow

**Purpose:** Step-by-step walkthrough of a single clearing event, showing how netting works and why only net demand hits the LP.

**Layout:** Five columns, left to right, connected by arrows.

### Step 1: Orders Accumulate
- Multiple buyer/seller icons with amounts feeding into Qb and Qs bars
- Example: Qb = 150, Qs = 100

### Step 2: Clearing Triggered
- A "Trigger" actor (anyone) initiates clearing
- Label: "Once per block, earns tx fee"

### Step 3: Netting
- Qb and Qs compared
- Matched portion (100 units) shown as crossing arrows between Qb and Qs, labeled "Netted — no LP needed"
- Remainder (Qb - Qs = 50) highlighted, labeled "Net demand"

### Step 4: LP Interaction
- Only the net 50 hits reserves
- X₀ → X₁ (reduced by 50 of token), Y₀ → Y₁ (increased per constant product)
- The 100 matched units bypass LP entirely

### Step 5: Unified Price
- All 150 buyers and 100 sellers receive the same post-clearing price
- Single price bar labeled "Unified price = post-swap spot price"

**Visual style:**
- Same color palette as Diagram 1
- Each step is a distinct column with connecting arrows
- Netting step (Step 3) visually emphasized with highlighted background
- Example numbers throughout for concreteness

## Technical Approach

- Static HTML files with inline CSS
- SVG for arrows, lines, and diagram elements where needed
- No JavaScript required (no interactivity)
- Self-contained — each file works standalone in a browser
- Clean enough to screenshot or print for slides

## Out of Scope

- Animation or interactivity
- MEV attack flow diagram (future)
- Liquidity efficiency comparison diagram (future)
- Smart contract implementation
- Mathematical formalization
