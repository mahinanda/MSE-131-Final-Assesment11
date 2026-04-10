import simpy
import random
import statistics

# ==========================================
# CHIPOTLE ASSEMBLY LINE SIMULATION
# BASELINE + 5 EXTENSIONS
# ==========================================

SEED = 42
SIM_DURATION = 300  # minutes = 5 hours

# Baseline average arrival rate
BASE_ARRIVAL_RATE = 1.5  # customers per minute

# Service times in minutes
SERVICE_TIMES = {
    "base": (15 / 60, 25 / 60),
    "protein": (17 / 60, 33 / 60),
    "toppings": (25 / 60, 45 / 60),
    "checkout": (15 / 60, 25 / 60)
}


# ==========================================
# HELPERS
# ==========================================
def avg(values):
    return statistics.mean(values) if values else 0


def draw_uniform_time(stage):
    low, high = SERVICE_TIMES[stage]
    return random.uniform(low, high)


# ==========================================
# SYSTEM CLASS
# ==========================================
class AssemblyLine:
    def __init__(
        self,
        env,
        rush_hour=False,
        customer_mix=False,
        extra_toppings_worker=False,
        refill_delay=False,
        fatigue=False
    ):
        self.env = env

        # Extension flags
        self.rush_hour = rush_hour
        self.customer_mix = customer_mix
        self.extra_toppings_worker = extra_toppings_worker
        self.refill_delay = refill_delay
        self.fatigue = fatigue

        # Resource capacities
        toppings_capacity = 2 if extra_toppings_worker else 1

        self.stations = {
            "base": simpy.Resource(env, capacity=1),
            "protein": simpy.Resource(env, capacity=1),
            "toppings": simpy.Resource(env, capacity=toppings_capacity),
            "checkout": simpy.Resource(env, capacity=1)
        }

        # Tracking
        self.waits = {k: [] for k in self.stations}
        self.busy = {k: 0 for k in self.stations}
        self.total_times = []
        self.completed = 0

        # For refill logic
        self.toppings_customers_since_refill = 0

    # -----------------------------
    # Customer type logic
    # -----------------------------
    def assign_customer_type(self):
        """
        Baseline: all customers are 'simple'
        Extension: 70% simple, 30% complex
        """
        if not self.customer_mix:
            return "simple"
        return "complex" if random.random() < 0.30 else "simple"

    # -----------------------------
    # Arrival rate logic
    # -----------------------------
    def current_arrival_rate(self):
        """
        Baseline: constant arrival rate
        Rush hour extension:
        - 0 to 120 min: normal
        - 120 to 210 min: rush hour
        - 210 to 300 min: normal
        """
        if not self.rush_hour:
            return BASE_ARRIVAL_RATE

        now = self.env.now
        if 120 <= now < 210:
            return 2.2  # rush hour
        return BASE_ARRIVAL_RATE

    # -----------------------------
    # Service time logic
    # -----------------------------
    def draw_service_time(self, stage, customer_type):
        service = draw_uniform_time(stage)

        # Extension: simple vs complex customers
        if self.customer_mix and customer_type == "complex":
            if stage == "base":
                service *= 1.10
            elif stage == "protein":
                service *= 1.20
            elif stage == "toppings":
                service *= 1.35
            elif stage == "checkout":
                service *= 1.05

        # Extension: worker fatigue
        # After 180 min, service slows down
        if self.fatigue:
            if 180 <= self.env.now < 240:
                service *= 1.10
            elif self.env.now >= 240:
                service *= 1.20

        return service

    # -----------------------------
    # Refill delay logic
    # -----------------------------
    def maybe_add_refill_delay(self, stage):
        """
        Extension: ingredient refill / stocking delay
        Every 25 customers at toppings, add a small refill pause.
        """
        if not self.refill_delay or stage != "toppings":
            return 0

        self.toppings_customers_since_refill += 1

        if self.toppings_customers_since_refill >= 25:
            self.toppings_customers_since_refill = 0
            return random.uniform(1.0, 2.0)  # 1 to 2 minute refill delay

        return 0

    # -----------------------------
    # Station visit
    # -----------------------------
    def visit_station(self, stage, resource, customer_type):
        start_wait = self.env.now

        with resource.request() as req:
            yield req

            wait_time = self.env.now - start_wait
            self.waits[stage].append(wait_time)

            # Optional refill delay
            refill = self.maybe_add_refill_delay(stage)
            if refill > 0:
                self.busy[stage] += refill
                yield self.env.timeout(refill)

            # Service time
            service = self.draw_service_time(stage, customer_type)
            self.busy[stage] += service
            yield self.env.timeout(service)

    # -----------------------------
    # Customer process
    # -----------------------------
    def process_customer(self, cid):
        arrival = self.env.now
        customer_type = self.assign_customer_type()

        for stage, resource in self.stations.items():
            yield self.env.process(self.visit_station(stage, resource, customer_type))

        total_time = self.env.now - arrival
        self.total_times.append(total_time)
        self.completed += 1


# ==========================================
# ARRIVAL PROCESS
# ==========================================
def generate_customers(env, system):
    cid = 0
    while True:
        rate = system.current_arrival_rate()
        gap = random.expovariate(rate)
        yield env.timeout(gap)

        cid += 1
        env.process(system.process_customer(cid))


# ==========================================
# SINGLE RUN
# ==========================================
def simulate(
    rush_hour=False,
    customer_mix=False,
    extra_toppings_worker=False,
    refill_delay=False,
    fatigue=False,
    seed=SEED
):
    random.seed(seed)

    env = simpy.Environment()
    system = AssemblyLine(
        env,
        rush_hour=rush_hour,
        customer_mix=customer_mix,
        extra_toppings_worker=extra_toppings_worker,
        refill_delay=refill_delay,
        fatigue=fatigue
    )

    env.process(generate_customers(env, system))
    env.run(until=SIM_DURATION)

    throughput = system.completed
    throughput_per_hour = throughput / (SIM_DURATION / 60)
    avg_total_time = avg(system.total_times)

    wait_stats = {k: avg(v) for k, v in system.waits.items()}
    utilization = {k: system.busy[k] / (SIM_DURATION * system.stations[k].capacity) for k in system.busy}

    return {
        "throughput": throughput,
        "throughput_per_hour": throughput_per_hour,
        "avg_total_time": avg_total_time,
        "waits": wait_stats,
        "utilization": utilization
    }


# ==========================================
# PRINT RESULTS
# ==========================================
def print_results(title, results):
    print(f"\n=== {title} ===")
    print(f"Total customers served: {results['throughput']}")
    print(f"Throughput/hour: {results['throughput_per_hour']:.2f}")
    print(f"Average total time: {results['avg_total_time']:.2f} min\n")

    print("Wait times:")
    for k, v in results["waits"].items():
        print(f"  {k.capitalize():<10}: {v:.2f} min")

    print("\nUtilization:")
    for k, v in results["utilization"].items():
        print(f"  {k.capitalize():<10}: {v:.2%}")


# ==========================================
# BUILD COMPACT SUMMARY ROWS
# ==========================================
def build_main_row(title, results):
    return {
        "Scenario": title,
        "Throughput/hr": round(results["throughput_per_hour"], 2),
        "Avg Total Time": round(results["avg_total_time"], 2),
    }


def build_bottleneck_row(title, results):
    return {
        "Scenario": title,
        "Toppings Wait": round(results["waits"]["toppings"], 2),
        "Toppings Util (%)": round(results["utilization"]["toppings"] * 100, 2),
    }


# ==========================================
# GENERIC TABLE PRINTER
# ==========================================
def print_table(title, rows, headers):
    # convert all values to strings
    str_rows = []
    for row in rows:
        str_row = {h: str(row[h]) for h in headers}
        str_rows.append(str_row)

    # column widths
    col_widths = {}
    for h in headers:
        col_widths[h] = max(len(h), max(len(r[h]) for r in str_rows))

    print(f"\n{title}")
    print("-" * sum(col_widths.values()) + "-" * (3 * (len(headers) - 1)))

    header_line = " | ".join(f"{h:<{col_widths[h]}}" for h in headers)
    print(header_line)
    print("-" * len(header_line))

    for row in str_rows:
        line = " | ".join(f"{row[h]:<{col_widths[h]}}" for h in headers)
        print(line)


# ==========================================
# RUN ALL MAIN CASES
# ==========================================
def run_all_cases():
    cases = [
        ("Baseline", {}),
        ("Rush Hour", {"rush_hour": True}),
        ("Simple vs Complex", {"customer_mix": True}),
        ("Extra Toppings Worker", {"extra_toppings_worker": True}),
        ("Refill Delay", {"refill_delay": True}),
        ("Worker Fatigue", {"fatigue": True}),
        
        # 🔥 ADDED SCENARIO (THIS IS THE IMPORTANT ONE)
        ("Rush Hour + Extra Toppings Worker", {"rush_hour": True, "extra_toppings_worker": True}),
    ]

    main_rows = []
    bottleneck_rows = []

    for title, settings in cases:
        results = simulate(**settings)
        print_results(title, results)

        main_rows.append(build_main_row(title, results))
        bottleneck_rows.append(build_bottleneck_row(title, results))

    print_table(
        "TABLE 1: MAIN SYSTEM OUTCOMES",
        main_rows,
        ["Scenario", "Throughput/hr", "Avg Total Time"]
    )

    print_table(
        "TABLE 2: BOTTLENECK-FOCUSED RESULTS",
        bottleneck_rows,
        ["Scenario", "Toppings Wait", "Toppings Util (%)"]
    )


if __name__ == "__main__":
    run_all_cases()