import simpy
import random
import statistics

# ==========================================
# FAST-CASUAL ASSEMBLY LINE SIMULATION
# ==========================================

# -------- SETTINGS --------
SEED = 42
SIM_DURATION = 300  # minutes (5 hours)
ARRIVAL_RATE = 1.5  # customers per minute

SERVICE_TIMES = {
    "base": (15/60, 25/60),
    "protein": (17/60, 33/60),
    "toppings": (25/60, 45/60),
    "checkout": (15/60, 25/60)
}


# -------- HELPERS --------
def draw_service_time(stage):
    low, high = SERVICE_TIMES[stage]
    return random.uniform(low, high)


def avg(values):
    return statistics.mean(values) if values else 0


# -------- SYSTEM CLASS --------
class AssemblyLine:
    def __init__(self, env):
        self.env = env

        # resources (1 worker each)
        self.stations = {
            "base": simpy.Resource(env, capacity=1),
            "protein": simpy.Resource(env, capacity=1),
            "toppings": simpy.Resource(env, capacity=1),
            "checkout": simpy.Resource(env, capacity=1)
        }

        # tracking
        self.waits = {k: [] for k in self.stations}
        self.busy = {k: 0 for k in self.stations}
        self.total_times = []
        self.completed = 0

    def visit_station(self, name, station):
        start_wait = self.env.now

        with station.request() as req:
            yield req

            wait_time = self.env.now - start_wait
            self.waits[name].append(wait_time)

            service = draw_service_time(name)
            self.busy[name] += service

            yield self.env.timeout(service)

    def process_customer(self, cid):
        arrival = self.env.now

        for name, station in self.stations.items():
            yield self.env.process(self.visit_station(name, station))

        total_time = self.env.now - arrival
        self.total_times.append(total_time)
        self.completed += 1


# -------- ARRIVAL PROCESS --------
def generate_customers(env, system):
    cid = 0
    while True:
        gap = random.expovariate(ARRIVAL_RATE)
        yield env.timeout(gap)

        cid += 1
        env.process(system.process_customer(cid))


# -------- MAIN RUN --------
def simulate():
    random.seed(SEED)

    env = simpy.Environment()
    system = AssemblyLine(env)

    env.process(generate_customers(env, system))
    env.run(until=SIM_DURATION)

    # results
    throughput = system.completed
    per_hour = throughput / (SIM_DURATION / 60)
    avg_time = avg(system.total_times)

    wait_stats = {k: avg(v) for k, v in system.waits.items()}
    utilization = {k: system.busy[k] / SIM_DURATION for k in system.busy}

    # output
    print("\n=== SIMULATION RESULTS ===")
    print(f"Total customers served: {throughput}")
    print(f"Throughput/hour: {per_hour:.2f}")
    print(f"Average total time: {avg_time:.2f} min\n")

    print("Wait times:")
    for k, v in wait_stats.items():
        print(f"  {k.capitalize():<10}: {v:.2f} min")

    print("\nUtilization:")
    for k, v in utilization.items():
        print(f"  {k.capitalize():<10}: {v:.2%}")

    if system.total_times:
        print(f"\nMin time: {min(system.total_times):.2f}")
        print(f"Max time: {max(system.total_times):.2f}")


if __name__ == "__main__":
    simulate()