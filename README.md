# ⚡ CapacityClaim: Powering the MWNTCOIN Protocol

Built for the EasyA Kickstart Hackathon

CapacityClaim is the infrastructure for **MWNTCOIN (MWNT)**—the world’s first tokenised, stablecoin-style compute claim. We are solving the "financialization of compute" by transforming raw GPU power into a liquid, tradeable, and redeemable Solana-native asset.

## 📖 TL;DR: What is MWNTCOIN?

The AI compute market is broken. TradFi offers futures you can't use, and DePIN offers rentals you can't trade. MWNT bridges this gap.

MWNTCOIN is a standardized capacity claim where:

1. **1 MWNT = 1 Hour of H100 GPU Compute (Standardized Unit).**
2. **Minted by Providers:** Verified data centers mint MWNT by proving they have the hardware.
3. **Traded by Speculators:** MWNT flows freely on Solana DEXs, providing deep liquidity for the AI industry.
4. **Burned by AI Labs:** Developers buy and "burn" MWNT to unlock physical server access.

## 🏗️ Architecture & Protocol Flow

### 1) The MWNT Minting Engine (Supply)

- **Hardware Attestation:** Providers use our `tee-mock` service to submit hardware proofs.
- **Whitelisted Mint:** Upon verification, the protocol mints MWNT tokens to the provider.
- **The Peg:** Unlike volatile DePIN tokens, MWNT is designed to track the "Fair Market Price" of an H100-hour, anchored by an on-chain price oracle.

### 2) The MWNT Secondary Market (Liquidity)

- **Unrestricted Trading:** While minting and redeeming are whitelisted for safety, MWNT itself is a standard SPL token.
- **Speculation-as-a-Service:** Traders can provide liquidity for MWNT on Raydium/Meteora without ever needing to touch a GPU, ensuring AI labs always have a liquid market to buy the compute they need.

### 3) The "Burn-to-Claim" Portal (Delivery)

- **Whitelisted Redemption:** To prevent abuse, only verified users (authenticated via Civic/SBTs) can burn MWNT.
- **Guaranteed Delivery:** Burning MWNT triggers a "Proof of Delivery" smart contract, releasing SSH credentials or an API endpoint to the user.

## 🛠️ Tech Stack

- **Token:** MWNTCOIN (MWNT) - Solana SPL Standard.
- **Smart Contracts:** Rust / Anchor Framework (minting logic, burn-for-delivery).
- **Identity:** Civic Pass for whitelisted redemption.
- **Frontend:** Next.js dashboard for providers (mint) and developers (burn).
- **Oracle:** Simulated Silicon-Data feed to track the MWNT price peg.

## 📂 Repository Structure

- `/programs`: Core logic for the MWNT mint/redeem protocol.
- `/app`: Frontend UI for the MWNTCOIN marketplace.
- `/tests`: Anchor tests simulating the MWNT lifecycle (mint -> trade -> burn).
- `/tee-mock`: Hardware verification simulation for MWNT providers.

## 🚀 Quick Start (Local Development)

### 1) Build the MWNT Protocol

```bash
anchor build
```

### 2) Deploy to Local Validator

```bash
solana-test-validator
anchor deploy
```

### 3) Launch the MWNT Dashboard

```bash
cd app
yarn install
yarn dev
```

## 🏆 Why MWNTCOIN Wins the White Space

The market is saturated with "rental shops" (Akash, CapIX) and "cash-settled indices" (CME). MWNTCOIN occupies the only unoccupied territory: the redeemable commodity.

| Feature         | Rental Marketplaces (CapIX/Akash) | Financial Indices (CME) | **MWNTCOIN**           |
| :-------------- | :-------------------------------- | :---------------------- | :--------------------- |
| **Tradeable?**  | No (rentals are static)           | Yes (cash-settled)      | **YES**                |
| **Redeemable?** | Yes                               | No                      | **YES**                |
| **Liquidity?**  | Low (peer-to-peer)                | High (institutional)    | **HIGH (DeFi-Native)** |

MWNT is the "Brent Crude" of the AI era. We don't just rent GPUs; we tokenize the future of intelligence.

## 💡 Strategy Note for Your Pitch

When judges ask what MWNT stands for, you can say it represents **"Minted Watt-Network Token"** or simply **"The MWNT Standard."** Emphasize that the token already exists on Solana, making this hackathon entry a shipped protocol rather than just a concept.
