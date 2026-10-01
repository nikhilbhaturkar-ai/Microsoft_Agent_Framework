import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from typing_extensions import Never
from dataclasses import dataclass
from agent_framework import WorkflowBuilder, WorkflowContext, WorkflowOutputEvent, executor

# Import our utilities
import sys
sys.path.append(str(Path(__file__).parent))
from invoice_utils import (
    InvoiceConfig, InvoiceData, read_invoices_csv, calculate_invoice_totals,
    render_invoice_text, save_invoice_file, log_action, ensure_directories,
    print_step, print_invoice_summary
)

# Load environment
load_dotenv('.env03')

# Directories
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
LOGS_DIR = BASE_DIR / "logs"

# Global state for interactive processing
selected_invoice_id = None


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def show_menu(invoices: list[InvoiceData]) -> str:
    """Display invoice selection menu and return selected ID."""
    print("\n" + "="*80)
    print("📋 AVAILABLE INVOICES")
    print("="*80)
    
    for idx, inv in enumerate(invoices, 1):
        preferred_badge = "⭐" if inv.is_preferred else "  "
        print(f"{idx}. {preferred_badge} {inv.invoice_id} - {inv.client_name}")
        print(f"   Amount: ${inv.subtotal:.2f} | Date: {inv.date}")
        print()
    
    while True:
        try:
            choice = input(f"Select invoice (1-{len(invoices)}): ").strip()
            idx = int(choice)
            if 1 <= idx <= len(invoices):
                return invoices[idx - 1].invoice_id
            else:
                print(f"❌ Please enter a number between 1 and {len(invoices)}")
        except ValueError:
            print("❌ Please enter a valid number")


def wait_for_user(step_name: str):
    """Pause and wait for user to press Enter."""
    print(f"\n{'─'*80}")
    input(f"⏸️  Press ENTER to continue to: {step_name} ▶️  ")
    print(f"{'─'*80}\n")


# ============================================================================
# SEQUENTIAL WORKFLOW EXECUTORS
# ============================================================================

@executor(id="load_config")
async def load_configuration(start_signal: str, ctx: WorkflowContext[InvoiceConfig]) -> None:
    """Step 1: Load configuration from environment."""
    print_step(1, "LOAD CONFIGURATION")
    print("🔧 Loading configuration...")
    
    config = InvoiceConfig()
    
    print(f"\n✅ Configuration loaded successfully!")
    print(f"   📊 Tax Rate: {config.tax_rate * 100}%")
    print(f"   💰 High Value Threshold: ${config.high_value_threshold:.2f}")
    print(f"   🎁 High Value Discount: {config.high_value_discount * 100}%")
    print(f"   ⭐ Preferred Client Discount: {config.preferred_client_discount * 100}%")
    
    log_action(f"Configuration loaded: {config}", str(LOGS_DIR))
    
    wait_for_user("STEP 2 - Read Invoice Data")
    
    await ctx.send_message(config)


@executor(id="read_invoices")
async def read_invoice_data(config: InvoiceConfig, ctx: WorkflowContext[tuple[InvoiceConfig, InvoiceData]]) -> None:
    """Step 2: Read and select a single invoice from CSV."""
    print_step(2, "READ INVOICE DATA & SELECT")
    print("📂 Reading invoices from CSV file...")
    
    csv_path = DATA_DIR / "invoices.csv"
    all_invoices = read_invoices_csv(str(csv_path))
    
    print(f"\n✅ Loaded {len(all_invoices)} invoices from {csv_path.name}")
    
    # Let user select invoice
    global selected_invoice_id
    selected_invoice_id = show_menu(all_invoices)
    
    # Find the selected invoice
    selected_invoice = next(inv for inv in all_invoices if inv.invoice_id == selected_invoice_id)
    
    print(f"\n✅ Selected Invoice: {selected_invoice.invoice_id}")
    print(f"   Client: {selected_invoice.client_name}")
    print(f"   Email: {selected_invoice.client_email}")
    print(f"   Item: {selected_invoice.item_description}")
    print(f"   Quantity: {selected_invoice.quantity}")
    print(f"   Unit Price: ${selected_invoice.unit_price:.2f}")
    print(f"   Subtotal: ${selected_invoice.subtotal:.2f}")
    print(f"   Preferred Client: {'⭐ YES' if selected_invoice.is_preferred else '❌ NO'}")
    
    log_action(f"Selected invoice {selected_invoice_id} for processing", str(LOGS_DIR))
    
    wait_for_user("STEP 3 - Calculate Totals")
    
    # Pass config and SINGLE invoice
    await ctx.send_message((config, selected_invoice))


@executor(id="calculate_totals")
async def calculate_totals_step(data: tuple[InvoiceConfig, InvoiceData], 
                                ctx: WorkflowContext[tuple[InvoiceData, dict]]) -> None:
    """Step 3: Calculate totals for the selected invoice."""
    print_step(3, "CALCULATE TOTALS")
    
    config, invoice = data
    
    print(f"🧮 Calculating amounts for {invoice.invoice_id}...")
    print(f"   Starting Subtotal: ${invoice.subtotal:.2f}")
    
    totals = calculate_invoice_totals(invoice, config)
    
    print(f"\n✅ Calculation Complete!")
    print(f"\n   {'Item':<30} {'Amount':>15}")
    print(f"   {'-'*30} {'-'*15}")
    print(f"   {'Subtotal':<30} ${totals['subtotal']:>14,.2f}")
    
    if totals['high_value_discount'] > 0:
        print(f"   {'High Value Discount (5%)':<30} -${totals['high_value_discount']:>13,.2f}")
    
    if totals['preferred_discount'] > 0:
        print(f"   {'Preferred Discount (3%)':<30} -${totals['preferred_discount']:>13,.2f}")
    
    if totals['total_discount'] > 0:
        print(f"   {'-'*30} {'-'*15}")
        print(f"   {'Amount After Discounts':<30} ${totals['amount_after_discount']:>14,.2f}")
    
    print(f"   {'Tax (10%)':<30} ${totals['tax']:>14,.2f}")
    print(f"   {'='*30} {'='*15}")
    print(f"   {'💰 TOTAL DUE':<30} ${totals['total']:>14,.2f}")
    print(f"   {'='*30} {'='*15}")
    
    log_action(f"Calculated totals for {invoice.invoice_id}: ${totals['total']:.2f}", str(LOGS_DIR))
    
    wait_for_user("STEP 4 - Render Invoice")
    
    await ctx.send_message((invoice, totals))


@executor(id="render_invoice")
async def render_invoice_step(data: tuple[InvoiceData, dict], 
                              ctx: WorkflowContext[tuple[InvoiceData, dict, str]]) -> None:
    """Step 4: Render the invoice as formatted text."""
    print_step(4, "RENDER INVOICE")
    
    invoice, totals = data
    config = InvoiceConfig()
    
    print(f"🖨️  Rendering invoice {invoice.invoice_id} as formatted text...")
    
    invoice_text = render_invoice_text(invoice, totals, config)
    
    print(f"\n✅ Invoice rendered successfully! ({len(invoice_text)} characters)")
    
    # Show preview
    print(f"\n{'─'*80}")
    print("📄 INVOICE PREVIEW:")
    print(f"{'─'*80}")
    print(invoice_text)
    print(f"{'─'*80}")
    
    log_action(f"Rendered invoice {invoice.invoice_id}", str(LOGS_DIR))
    
    wait_for_user("STEP 5 - Save Invoice")
    
    await ctx.send_message((invoice, totals, invoice_text))


@executor(id="save_invoice")
async def save_invoice_step(data: tuple[InvoiceData, dict, str], 
                            ctx: WorkflowContext[Never, str]) -> None:
    """Step 5: Save the invoice to output directory."""
    print_step(5, "SAVE INVOICE")
    
    invoice, totals, invoice_text = data
    ensure_directories(str(OUTPUT_DIR), str(LOGS_DIR))
    
    print(f"💾 Saving invoice {invoice.invoice_id} to disk...")
    
    filepath = save_invoice_file(invoice.invoice_id, invoice_text, str(OUTPUT_DIR))
    
    print(f"\n✅ Invoice saved successfully!")
    print(f"   📁 Location: {filepath}")
    print(f"   📊 Client: {invoice.client_name}")
    print(f"   💵 Amount: ${totals['total']:.2f}")
    
    log_action(f"Saved invoice {invoice.invoice_id} to {filepath}", str(LOGS_DIR))
    
    # Yield final output
    summary = f"✅ Sequential workflow completed! Invoice {invoice.invoice_id} processed successfully."
    await ctx.yield_output(summary)


# ============================================================================
# MAIN WORKFLOW
# ============================================================================

async def run_workflow():
    """Run the sequential invoice workflow for ONE selected invoice."""
    
    # Build the sequential workflow
    workflow = (
        WorkflowBuilder()
        .set_start_executor(load_configuration)
        .add_edge(load_configuration, read_invoice_data)
        .add_edge(read_invoice_data, calculate_totals_step)
        .add_edge(calculate_totals_step, render_invoice_step)
        .add_edge(render_invoice_step, save_invoice_step)
        .build()
    )
    
    # Run the workflow
    async for event in workflow.run_stream("start"):
        if isinstance(event, WorkflowOutputEvent):
            print("\n" + "="*80)
            print("🎉 WORKFLOW COMPLETE")
            print("="*80)
            print(event.data)
            print("\n📁 Check the following directories:")
            print(f"   • Output: {OUTPUT_DIR}")
            print(f"   • Logs: {LOGS_DIR}")
            print("="*80)


async def main():
    """Main entry point with loop for multiple invoices."""
    
    print("\n" + "="*80)
    print("🧾 INVOICE BUILDER - INTERACTIVE SEQUENTIAL WORKFLOW")
    print("="*80)
    print("\n✨ This demo shows a sequential workflow with INTERACTIVE steps:")
    print("   • You select ONE invoice to process")
    print("   • Each workflow step pauses for you to review")
    print("   • Press ENTER to proceed to the next step")
    print("   • See intermediate results at each stage")
    print("\n📋 Workflow Steps:")
    print("   1. Load Configuration → Shows tax rates and discounts")
    print("   2. Read & Select Invoice → Choose from menu")
    print("   3. Calculate Totals → See breakdown of amounts")
    print("   4. Render Invoice → Preview formatted invoice")
    print("   5. Save Invoice → Write to output file")
    print("="*80)
    
    while True:
        # Run one invoice through the workflow
        await run_workflow()
        
        # Ask if user wants to process another
        print("\n" + "="*80)
        choice = input("\n🔄 Process another invoice? (y/n): ").strip().lower()
        
        if choice != 'y':
            print("\n👋 Thank you for using Invoice Builder!")
            print("="*80)
            break
        
        print("\n" + "="*80)
        print("🔄 RESTARTING WORKFLOW...")
        print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
