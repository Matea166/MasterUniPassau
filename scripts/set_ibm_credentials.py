from qiskit_ibm_runtime import QiskitRuntimeService

apiKey = ""
crn = ""

QiskitRuntimeService.save_account(token=apiKey, instance=crn, overwrite=True)

print("done")
