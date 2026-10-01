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

# Load environment
load_dotenv('.env03')

# Directories
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
LOGS_DIR = BASE_DIR / "logs"

# Global state for interactive processing
# selected_invoice_id = None

class CustomerData:
    """Represents a customer."""
    def __init__(self, name: str, id: str, preferred: bool):
        self.name = name
        self.id = id
        self.preferred = preferred
    
    def __repr__(self):
        return f"CustomerData(name={self.name}, id={self.id}, preferred={self.preferred})"

class OrderData:
    """Represents an order."""
    def __init__(self, order_id: str, customer_id: str, items: list):
        self.order_id = order_id
        self.customer_id = customer_id
        self.items = items
    
    def __repr__(self):
        return f"OrderData(order_id={self.order_id}, customer_id={self.customer_id}, items={self.items})"
    
class InvoiceData:
    """Represents a single invoice record."""
    def __init__(self, invoice_id: str, client_name: str, client_email: str,
                 is_preferred: bool, item_description: str, quantity: int,
                 unit_price: float, date: str):
        self.invoice_id = invoice_id
        self.client_name = client_name
        self.client_email = client_email
        self.is_preferred = is_preferred
        self.item_description = item_description
        self.quantity = quantity
        self.unit_price = unit_price
        self.date = date

    def __repr__(self):
        return (f"InvoiceData(invoice_id={self.invoice_id}, client_name={self.client_name}, "
                f"client_email={self.client_email}, is_preferred={self.is_preferred}, "
                f"item_description={self.item_description}, quantity={self.quantity}, "
                f"unit_price={self.unit_price}, date={self.date})")

def wait_for_user(step_name: str):
    """Pause and wait for user to press Enter."""
    print(f"\n{'─'*80}")
    input(f"⏸️  Press ENTER to continue to: {step_name} ▶️  ")
    print(f"{'─'*80}\n")


# ============================================================================
# SEQUENTIAL WORKFLOW EXECUTORS
# ============================================================================

@executor(id="customer_onboarding")
async def customer_onboarding(start_signal: str, ctx: WorkflowContext[CustomerData]) -> None:
    """Step 1: Customer Onboarding."""
    
    customer=CustomerData("Acme Corp","CUST1001",True)
    print("Customer Onboarding Completed:", customer)

    wait_for_user("STEP 2 - Proceed to order processing")
    
    await ctx.send_message(customer)


@executor(id="order_processing")
async def order_processing(customer: CustomerData, ctx: WorkflowContext[OrderData]) -> None:
    """Step 2: Take the order for customer and save it."""
    
    order=OrderData("ORDER1001",customer.id,["Item A","Item B"])
    print("Order Processing Completed:", order)    
    wait_for_user("STEP 3 - Proceed to checkout orders")
    
    await ctx.send_message(order)


@executor(id="checkout_orders")
async def checkout_orders(data: OrderData, 
                                ctx: WorkflowContext[InvoiceData]) -> None:
    """Step 3: Checkout the order and generate invoice data."""

    invoice=InvoiceData("INV1001","Acme Corp","email1",True,"Item A",2,50.0,"2024-01-01")
    print("Checkout Orders Completed:", invoice)
    
    wait_for_user("STEP 4 - proceed to print invoice")
    
    await ctx.send_message(invoice)


@executor(id="print_invoice")
async def print_invoice(data: InvoiceData, 
                              ctx: WorkflowContext[Never,str]) -> None:
    """Step 4: Print the invoice for review."""
    invoice = data
    
    print("Invoice has been generated:", invoice)
    
    await ctx.yield_output("Sequential Flow is completed successfully!")


# ============================================================================
# MAIN WORKFLOW
# ============================================================================

async def run_workflow():
    """Run the sequential invoice workflow for ONE selected invoice."""
    
    # Build the sequential workflow
    workflow = (
        WorkflowBuilder()
        .set_start_executor(customer_onboarding)
        .add_edge(customer_onboarding, order_processing)
        .add_edge(order_processing, checkout_orders)
        .add_edge(checkout_orders, print_invoice)
        .build()
    )
    
    # Run the workflow
    async for event in workflow.run_stream("start"):
        if isinstance(event, WorkflowOutputEvent):
            print("\n" + "="*80)
            print("🎉 WORKFLOW COMPLETE")
            print("="*80)
            print(event.data)
            print("="*80)


async def main():
    """Main entry point with loop for multiple invoices."""
    
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
